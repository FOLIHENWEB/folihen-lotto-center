from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from master_data_reader import (
    get_master_data_files,
    parse_date,
    parse_draw_numbers,
    read_document,
)


# ============================================================
# TOC PHASE 3 — CANONICAL NORMALIZED DATA LAYER
# ============================================================

EXPECTED_GAME_COUNT = 19
EXPECTED_COLUMNS = 2
EXPECTED_DRAW_COUNT = 5

SCHEMA_NAME = "toc.normalized_master_data"
SCHEMA_VERSION = 1

BACKEND_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BACKEND_DIR / "data"
OUTPUT_JSON = OUTPUT_DIR / "normalized_master_data.json"


# ============================================================
# CANONICAL MODELS
# ============================================================

@dataclass(frozen=True)
class NormalizedDraw:
    game: str
    source_file: str
    source_table: int
    source_row: int
    source_date_text: str
    source_draw_text: str
    draw_date: str
    draw_numbers: list[int]


@dataclass
class NormalizedGame:
    game: str
    source_file: str
    source_sha256: str
    record_count: int
    records: list[NormalizedDraw]


# ============================================================
# GENERAL HELPERS
# ============================================================

def clean_text(value: Any) -> str:
    if value is None:
        return ""

    return " ".join(str(value).split()).strip()


def sha256_file(file_path: Path) -> str:
    """
    Calculate the SHA-256 fingerprint of a source DOCX.
    """

    digest = hashlib.sha256()

    with file_path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def canonical_payload(dataset: dict[str, Any]) -> dict[str, Any]:
    """
    Return only the fields that define the identity of the
    canonical normalized dataset.

    Build time and output metadata deliberately do not affect
    canonical data identity.
    """

    return {
        "schema": dataset["schema"],
        "schema_version": dataset["schema_version"],
        "game_count": dataset["game_count"],
        "record_count": dataset["record_count"],
        "games": dataset["games"],
    }


def calculate_dataset_sha256(
    dataset: dict[str, Any],
) -> str:
    """
    Calculate deterministic SHA-256 identity of canonical data.
    """

    payload = canonical_payload(dataset)

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


# ============================================================
# SOURCE NORMALIZATION
# ============================================================

def normalize_game(file_path: Path) -> NormalizedGame:
    """
    Read and normalize one MASTER_DATA DOCX exactly once.

    The source document is never modified.
    """

    document_data = read_document(file_path)

    game_name = file_path.stem.strip()

    if not game_name:
        raise ValueError(
            f"Invalid empty game name: {file_path}"
        )

    records: list[NormalizedDraw] = []

    source_data_row_count = 0

    if not document_data["tables"]:
        raise ValueError(
            f"{file_path.name}: no tables found"
        )

    for table_number, table in enumerate(
        document_data["tables"],
        start=1,
    ):
        if not table:
            continue

        header = table[0]

        if len(header) != EXPECTED_COLUMNS:
            raise ValueError(
                f"{file_path.name}: table {table_number} "
                f"header has {len(header)} columns; "
                f"expected {EXPECTED_COLUMNS}"
            )

        normalized_header = [
            clean_text(value).casefold()
            for value in header
        ]

        expected_header = [
            "date",
            "draw numbers",
        ]

        if normalized_header != expected_header:
            raise ValueError(
                f"{file_path.name}: table {table_number} "
                f"unexpected header {header!r}; "
                f"expected ['Date', 'Draw Numbers']"
            )

        for source_row, row in enumerate(
            table[1:],
            start=2,
        ):
            if not any(clean_text(value) for value in row):
                continue

            source_data_row_count += 1

            if len(row) != EXPECTED_COLUMNS:
                raise ValueError(
                    f"{file_path.name}: "
                    f"table {table_number}, "
                    f"row {source_row}: "
                    f"expected {EXPECTED_COLUMNS} columns, "
                    f"found {len(row)}"
                )

            source_date_text = clean_text(row[0])
            source_draw_text = clean_text(row[1])

            parsed_date = parse_date(
                source_date_text
            )

            if parsed_date is None:
                raise ValueError(
                    f"{file_path.name}: "
                    f"table {table_number}, "
                    f"row {source_row}: "
                    f"invalid date "
                    f"{source_date_text!r}"
                )

            draw_numbers = parse_draw_numbers(
                source_draw_text
            )

            if draw_numbers is None:
                raise ValueError(
                    f"{file_path.name}: "
                    f"table {table_number}, "
                    f"row {source_row}: "
                    f"invalid draw "
                    f"{source_draw_text!r}"
                )

            if len(draw_numbers) != EXPECTED_DRAW_COUNT:
                raise ValueError(
                    f"{file_path.name}: "
                    f"table {table_number}, "
                    f"row {source_row}: "
                    f"expected {EXPECTED_DRAW_COUNT} "
                    f"draw numbers, "
                    f"found {len(draw_numbers)}"
                )

            if not all(
                isinstance(number, int)
                and not isinstance(number, bool)
                for number in draw_numbers
            ):
                raise ValueError(
                    f"{file_path.name}: "
                    f"table {table_number}, "
                    f"row {source_row}: "
                    "draw contains non-integer values"
                )

            records.append(
                NormalizedDraw(
                    game=game_name,
                    source_file=file_path.name,
                    source_table=table_number,
                    source_row=source_row,
                    source_date_text=source_date_text,
                    source_draw_text=source_draw_text,
                    draw_date=parsed_date.isoformat(),
                    draw_numbers=list(draw_numbers),
                )
            )

    if not records:
        raise ValueError(
            f"{file_path.name}: "
            "no historical draw records found"
        )

    if len(records) != source_data_row_count:
        raise ValueError(
            f"{file_path.name}: "
            "source-to-normalized count mismatch: "
            f"{source_data_row_count} source rows versus "
            f"{len(records)} normalized records"
        )

    records.sort(
        key=lambda record: (
            record.draw_date,
            record.source_table,
            record.source_row,
        )
    )

    return NormalizedGame(
        game=game_name,
        source_file=file_path.name,
        source_sha256=sha256_file(file_path),
        record_count=len(records),
        records=records,
    )


# ============================================================
# DUPLICATE / CONFLICT VALIDATION
# ============================================================

def validate_duplicates_and_conflicts(
    games: list[NormalizedGame],
) -> None:
    """
    Detect two different integrity problems:

    1. Exact duplicate:
      same game + same date + same numbers.

    2. Date conflict:
      same game + same date but different numbers.

    Both are rejected rather than silently resolved.
    """

    exact_seen: dict[
        tuple[str, str, tuple[int, ...]],
        NormalizedDraw,
    ] = {}

    date_seen: dict[
        tuple[str, str],
        NormalizedDraw,
    ] = {}

    for game in games:
        for record in game.records:

            exact_key = (
                record.game.casefold(),
                record.draw_date,
                tuple(record.draw_numbers),
            )

            if exact_key in exact_seen:
                first = exact_seen[exact_key]

                raise ValueError(
                    "Exact duplicate historical draw: "
                    f"game={record.game!r}, "
                    f"date={record.draw_date}, "
                    f"numbers={record.draw_numbers}; "
                    f"first at table "
                    f"{first.source_table}, "
                    f"row {first.source_row}; "
                    f"again at table "
                    f"{record.source_table}, "
                    f"row {record.source_row}"
                )

            exact_seen[exact_key] = record

            date_key = (
                record.game.casefold(),
                record.draw_date,
            )

            previous = date_seen.get(date_key)

            if previous is not None:
                if (
                    previous.draw_numbers
                    != record.draw_numbers
                ):
                    
                    raise ValueError(
                        "Conflicting historical draws for the same game/date: "
                        f"game={record.game!r}, "
                        f"date={record.draw_date}; "
                        f"FIRST: table={previous.source_table}, "
                        f"row={previous.source_row}, "
                        f"raw_date={previous.source_date_text!r}, "
                        f"numbers={previous.draw_numbers}; "
                        f"SECOND: table={record.source_table}, "
                        f"row={record.source_row}, "
                        f"raw_date={record.source_date_text!r}, "
                        f"numbers={record.draw_numbers}"
                    )
            else:
                date_seen[date_key] = record


# ============================================================
# BUILD CANONICAL DATASET
# ============================================================

def build_normalized_dataset() -> dict[str, Any]:
    """
    Build the complete canonical TOC MASTER_DATA dataset.
    """

    source_files = get_master_data_files()

    if len(source_files) != EXPECTED_GAME_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_GAME_COUNT} "
            f"MASTER_DATA games, "
            f"found {len(source_files)}"
        )

    games: list[NormalizedGame] = []

    game_names: set[str] = set()

    for file_path in source_files:
        normalized_game = normalize_game(
            file_path
        )

        game_key = normalized_game.game.casefold()

        if game_key in game_names:
            raise ValueError(
                "Duplicate canonical game name: "
                f"{normalized_game.game!r}"
            )

        game_names.add(game_key)

        games.append(normalized_game)

    games.sort(
        key=lambda game: game.game.casefold()
    )

    validate_duplicates_and_conflicts(
        games
    )

    total_records = sum(
        game.record_count
        for game in games
    )

    dataset: dict[str, Any] = {
        "schema": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "game_count": len(games),
        "record_count": total_records,
        "games": [],
    }

    for game in games:
        dataset["games"].append(
            {
                "game": game.game,
                "source": {
                    "file": game.source_file,
                    "sha256": game.source_sha256,
                },
                "record_count": game.record_count,
                "records": [
                    asdict(record)
                    for record in game.records
                ],
            }
        )

    dataset["dataset_sha256"] = (
        calculate_dataset_sha256(dataset)
    )

    return dataset


# ============================================================
# CANONICAL DATASET VALIDATION
# ============================================================

def validate_normalized_dataset(
    dataset: dict[str, Any],
) -> None:
    """
    Validate the final canonical representation.
    """

    if dataset.get("schema") != SCHEMA_NAME:
        raise ValueError(
            "Canonical schema name mismatch"
        )

    if dataset.get(
        "schema_version"
    ) != SCHEMA_VERSION:
        raise ValueError(
            "Canonical schema version mismatch"
        )

    games = dataset.get("games")

    if not isinstance(games, list):
        raise ValueError(
            "'games' must be a list"
        )

    if len(games) != EXPECTED_GAME_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_GAME_COUNT} games, "
            f"found {len(games)}"
        )

    if dataset.get(
        "game_count"
    ) != len(games):
        raise ValueError(
            "game_count does not match games length"
        )

    total_records = 0
    game_names: set[str] = set()

    for game in games:

        game_name = game.get("game")

        if (
            not isinstance(game_name, str)
            or not game_name.strip()
        ):
            raise ValueError(
                "Invalid canonical game name"
            )

        game_key = game_name.casefold()

        if game_key in game_names:
            raise ValueError(
                f"Duplicate game: {game_name!r}"
            )

        game_names.add(game_key)

        source = game.get("source")

        if not isinstance(source, dict):
            raise ValueError(
                f"{game_name}: missing source metadata"
            )

        source_file = source.get("file")
        source_hash = source.get("sha256")

        if (
            not isinstance(source_file, str)
            or not source_file.lower().endswith(
                ".docx"
            )
        ):
            raise ValueError(
                f"{game_name}: invalid source file"
            )

        if (
            not isinstance(source_hash, str)
            or not re_full_sha256(source_hash)
        ):
            raise ValueError(
                f"{game_name}: invalid source SHA-256"
            )

        records = game.get("records")

        if not isinstance(records, list):
            raise ValueError(
                f"{game_name}: records must be a list"
            )

        if not records:
            raise ValueError(
                f"{game_name}: no records"
            )

        if game.get(
            "record_count"
        ) != len(records):
            raise ValueError(
                f"{game_name}: "
                "record_count mismatch"
            )

        total_records += len(records)

        for record in records:

            if record.get("game") != game_name:
                raise ValueError(
                    f"{game_name}: "
                    "record game mismatch"
                )

            if record.get(
                "source_file"
            ) != source_file:
                raise ValueError(
                    f"{game_name}: "
                    "record source-file mismatch"
                )

            source_table = record.get(
                "source_table"
            )

            if (
                not isinstance(source_table, int)
                or isinstance(source_table, bool)
                or source_table < 1
            ):
                raise ValueError(
                    f"{game_name}: "
                    "invalid source_table"
                )

            source_row = record.get(
                "source_row"
            )

            if (
                not isinstance(source_row, int)
                or isinstance(source_row, bool)
                or source_row < 2
            ):
                raise ValueError(
                    f"{game_name}: "
                    "invalid source_row"
                )

            if not isinstance(
                record.get("source_date_text"),
                str,
            ):
                raise ValueError(
                    f"{game_name}: "
                    "invalid source_date_text"
                )

            if not isinstance(
                record.get("source_draw_text"),
                str,
            ):
                raise ValueError(
                    f"{game_name}: "
                    "invalid source_draw_text"
                )

            draw_date = record.get(
                "draw_date"
            )

            try:
                date.fromisoformat(draw_date)
            except (
                TypeError,
                ValueError,
            ) as exc:
                raise ValueError(
                    f"{game_name}: "
                    f"invalid ISO date "
                    f"{draw_date!r}"
                ) from exc

            numbers = record.get(
                "draw_numbers"
            )

            if not isinstance(numbers, list):
                raise ValueError(
                    f"{game_name}: "
                    "draw_numbers must be a list"
                )

            if len(numbers) != EXPECTED_DRAW_COUNT:
                raise ValueError(
                    f"{game_name}: "
                    f"expected {EXPECTED_DRAW_COUNT} "
                    "draw numbers"
                )

            if not all(
                isinstance(number, int)
                and not isinstance(number, bool)
                for number in numbers
            ):
                raise ValueError(
                    f"{game_name}: "
                    "draw_numbers must contain "
                    "integers only"
                )

    if dataset.get(
        "record_count"
    ) != total_records:
        raise ValueError(
            "Global record_count mismatch"
        )

    expected_hash = dataset.get(
        "dataset_sha256"
    )

    if (
        not isinstance(expected_hash, str)
        or not re_full_sha256(expected_hash)
    ):
        raise ValueError(
            "Invalid dataset SHA-256"
        )

    actual_hash = calculate_dataset_sha256(
        dataset
    )

    if actual_hash != expected_hash:
        raise ValueError(
            "Canonical dataset SHA-256 mismatch"
        )


def re_full_sha256(value: str) -> bool:
    """
    Validate a lowercase/uppercase 64-character SHA-256 string.
    """

    if len(value) != 64:
        return False

    try:
        int(value, 16)
        return True
    except ValueError:
        return False


# ============================================================
# ATOMIC WRITE
# ============================================================

def write_dataset_atomic(
    dataset: dict[str, Any],
) -> Path:
    """
    Write normalized_master_data.json atomically.

    Existing valid output is replaced only after the new file
    has been completely written and flushed.
    """

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    serialized = json.dumps(
        dataset,
        ensure_ascii=False,
        indent=2,
    )

    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=OUTPUT_DIR,
            prefix=".normalized_master_data_",
            suffix=".tmp",
            delete=False,
        ) as temp_file:

            temp_file.write(serialized)
            temp_file.write("\n")
            temp_file.flush()

            os.fsync(
                temp_file.fileno()
            )

            temp_path = Path(
                temp_file.name
            )

        os.replace(
            temp_path,
            OUTPUT_JSON,
        )

        temp_path = None

    finally:
        if (
            temp_path is not None
            and temp_path.exists()
        ):
            temp_path.unlink(
                missing_ok=True
            )

    return OUTPUT_JSON


# ============================================================
# POST-WRITE VERIFICATION
# ============================================================

def verify_written_dataset(
    output_path: Path,
) -> dict[str, Any]:
    """
    Reload and validate exactly what was written to disk.
    """

    with output_path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        dataset = json.load(handle)

    validate_normalized_dataset(
        dataset
    )

    return dataset


# ============================================================
# STATUS REPORTING
# ============================================================

def print_game_summary(
    dataset: dict[str, Any],
) -> None:

    print()
    print("=== GAME RECORD COUNTS ===")

    for game in dataset["games"]:
        print(
            f"{game['game']}: "
            f"{game['record_count']} records"
        )


def print_success(
    dataset: dict[str, Any],
    *,
    dry_run: bool,
    output_path: Path | None = None,
) -> None:

    print()
    print(
        "=== TOC PHASE 3: "
        "CANONICAL NORMALIZATION ==="
    )

    print(
        f"Schema:            "
        f"{dataset['schema']}"
    )

    print(
        f"Schema version:    "
        f"{dataset['schema_version']}"
    )

    print(
        f"Games normalized:  "
        f"{dataset['game_count']}"
    )

    print(
        f"Records normalized: "
        f"{dataset['record_count']}"
    )

    print(
        f"Dataset SHA-256:    "
        f"{dataset['dataset_sha256']}"
    )

    print_game_summary(
        dataset
    )

    print()

    print(
        "SOURCE PARSING: PASSED"
    )

    print(
        "SOURCE → NORMALIZED COUNT CHECK: PASSED"
    )

    print(
        "EXACT DUPLICATE CHECK: PASSED"
    )

    print(
        "SAME-DATE CONFLICT CHECK: PASSED"
    )

    print(
        "CANONICAL SCHEMA VALIDATION: PASSED"
    )

    if dry_run:
        print(
            "DRY RUN: PASSED — no output file written"
        )
    else:
        print(
            "ATOMIC WRITE: PASSED"
        )

        print(
            "POST-WRITE VERIFICATION: PASSED"
        )

        print(
            f"Output: {output_path}"
        )

    print()

    print(
        "TOC PHASE 3 NORMALIZATION: PASSED"
    )


# ============================================================
# EXECUTION
# ============================================================

def execute(
    *,
    dry_run: bool,
) -> int:

    try:
        dataset = build_normalized_dataset()

        validate_normalized_dataset(
            dataset
        )

        if dry_run:
            print_success(
                dataset,
                dry_run=True,
            )

            return 0

        output_path = write_dataset_atomic(
            dataset
        )

        written_dataset = (
            verify_written_dataset(
                output_path
            )
        )

        print_success(
            written_dataset,
            dry_run=False,
            output_path=output_path,
        )

        return 0

    except ValueError as exc:
        print()
        print(
            "TOC PHASE 3 NORMALIZATION: "
            "VALIDATION FAILED"
        )
        print(
            f"{type(exc).__name__}: {exc}"
        )

        return 2

    except OSError as exc:
        print()
        print(
            "TOC PHASE 3 NORMALIZATION: "
            "I/O FAILED"
        )
        print(
            f"{type(exc).__name__}: {exc}"
        )

        return 3

    except Exception as exc:
        print()
        print(
            "TOC PHASE 3 NORMALIZATION: "
            "FAILED"
        )
        print(
            f"{type(exc).__name__}: {exc}"
        )

        return 1


# ============================================================
# COMMAND LINE
# ============================================================

def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "TOC Phase 3 canonical MASTER_DATA "
            "normalization layer"
        )
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Build and fully validate the canonical "
            "dataset without writing the JSON output"
        ),
    )

    args = parser.parse_args()

    return execute(
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())