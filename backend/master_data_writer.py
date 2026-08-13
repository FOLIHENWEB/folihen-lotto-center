from __future__ import annotations

import shutil
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from docx import Document

from master_data_reader import (
    MASTER_DATA_DIR,
    get_master_data_files,
)


class MasterDataWriteError(RuntimeError):
    """Raised when a MASTER_DATA draw cannot be written safely."""


def _normalize_game_name(value: str) -> str:
    return " ".join(str(value).strip().lower().split())


def _parse_input_date(value: str) -> date:
    value = str(value).strip()

    if not value:
        raise MasterDataWriteError("Draw date is required.")

    accepted_formats = (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
    )

    for fmt in accepted_formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass

    raise MasterDataWriteError(
        "Invalid draw date. Use YYYY-MM-DD."
    )


def _format_master_date(value: date) -> str:
    suffix = "th"

    if value.day % 100 not in (11, 12, 13):
        suffix = {
            1: "st",
            2: "nd",
            3: "rd",
        }.get(value.day % 10, "th")

    return (
        f"{value.day}{suffix} "
        f"{value.strftime('%b')}, "
        f"{value.strftime('%y')}"
    )


def _validate_numbers(values: Iterable[object]) -> list[int]:
    try:
        numbers = [int(value) for value in values]
    except (TypeError, ValueError) as exc:
        raise MasterDataWriteError(
            "Draw numbers must be whole numbers."
        ) from exc

    if len(numbers) != 5:
        raise MasterDataWriteError(
            "Exactly five draw numbers are required."
        )

    if any(number < 1 or number > 90 for number in numbers):
        raise MasterDataWriteError(
            "Every draw number must be between 1 and 90."
        )

    # Repeated numbers are allowed because canonical historical
    # MASTER_DATA may legitimately contain repeated values.
    return numbers


def _resolve_game_file(game_name: str) -> Path:
    requested = _normalize_game_name(game_name)

    if not requested:
        raise MasterDataWriteError("Game is required.")

    matches: list[Path] = []

    for path in get_master_data_files():
        if _normalize_game_name(path.stem) == requested:
            matches.append(path)

    if not matches:
        raise MasterDataWriteError(
            f"MASTER_DATA file not found for game: {game_name}"
        )

    if len(matches) > 1:
        raise MasterDataWriteError(
            f"Multiple MASTER_DATA files matched game: {game_name}"
        )

    return matches[0]


def _existing_rows(path: Path) -> list[tuple[str, str]]:
    document = Document(path)

    if not document.tables:
        raise MasterDataWriteError(
            f"No MASTER_DATA table found in {path.name}"
        )

    table = document.tables[0]

    if len(table.columns) < 2:
        raise MasterDataWriteError(
            f"MASTER_DATA table in {path.name} does not have two columns."
        )

    rows: list[tuple[str, str]] = []

    for row in table.rows[1:]:
        cells = row.cells

        if len(cells) < 2:
            continue

        date_text = cells[0].text.strip()
        draw_text = cells[1].text.strip()

        if date_text or draw_text:
            rows.append((date_text, draw_text))

    return rows


def _parse_existing_date(value: str) -> date | None:
    text = str(value).strip()

    formats = (
        "%dth %b, %y",
        "%dst %b, %y",
        "%dnd %b, %y",
        "%drd %b, %y",
        "%d %b, %y",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
    )

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass

    cleaned = (
        text.replace("st ", " ")
        .replace("nd ", " ")
        .replace("rd ", " ")
        .replace("th ", " ")
    )

    try:
        return datetime.strptime(cleaned, "%d %b, %y").date()
    except ValueError:
        return None


def _parse_existing_numbers(
    value: str,
) -> tuple[int, ...] | None:
    cleaned = (
        str(value)
        .strip()
        .replace(",", "-")
        .replace(" ", "-")
    )

    parts = [
        part.strip()
        for part in cleaned.split("-")
        if part.strip()
    ]

    try:
        numbers = tuple(int(part) for part in parts)
    except ValueError:
        return None

    if len(numbers) != 5:
        return None

    return numbers


def _check_existing_draw(
    path: Path,
    draw_date: date,
    numbers: list[int],
) -> None:
    requested_numbers = tuple(numbers)

    parsed_rows: list[
        tuple[date, tuple[int, ...]]
    ] = []

    for date_text, draw_text in _existing_rows(path):
        existing_date = _parse_existing_date(date_text)
        existing_numbers = _parse_existing_numbers(draw_text)

        if existing_date is None or existing_numbers is None:
            continue

        parsed_rows.append(
            (existing_date, existing_numbers)
        )

        if existing_date == draw_date:
            if existing_numbers == requested_numbers:
                raise MasterDataWriteError(
                    "This draw already exists in MASTER_DATA."
                )

            raise MasterDataWriteError(
                "A different draw already exists for this game and date."
            )

    if parsed_rows:
        latest_date = max(
            row[0] for row in parsed_rows
        )

        if draw_date <= latest_date:
            raise MasterDataWriteError(
                "The new draw date must be later than the latest "
                f"existing draw ({latest_date.isoformat()})."
            )


def _atomic_save_document(
    document: Document,
    target: Path,
) -> None:
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with tempfile.NamedTemporaryFile(
        mode="wb",
        suffix=".docx",
        prefix=".master_data_",
        dir=str(target.parent),
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)

    try:
        document.save(temp_path)
        temp_path.replace(target)
    finally:
        if temp_path.exists():
            temp_path.unlink(
                missing_ok=True
            )


def append_draw(
    game_name: str,
    draw_date_value: str,
    draw_numbers: Iterable[object],
) -> dict:
    """
    Safely append one official draw to its MASTER_DATA DOCX.

    Repeated draw values are preserved if present.
    The caller is responsible for running normalization
    after this function succeeds.
    """

    if not MASTER_DATA_DIR.is_dir():
        raise MasterDataWriteError(
            f"MASTER_DATA folder not found: {MASTER_DATA_DIR}"
        )

    draw_date = _parse_input_date(
        draw_date_value
    )

    if draw_date > date.today():
        raise MasterDataWriteError(
            "The official draw date cannot be in the future."
        )

    numbers = _validate_numbers(
        draw_numbers
    )

    source_path = _resolve_game_file(
        game_name
    )

    _check_existing_draw(
        source_path,
        draw_date,
        numbers,
    )

    rows_before = _existing_rows(
        source_path
    )

    count_before = len(
        rows_before
    )

    backup_path = source_path.with_suffix(
        source_path.suffix
        + ".before_add_draw.bak"
    )

    shutil.copy2(
        source_path,
        backup_path,
    )

    try:
        document = Document(
            source_path
        )

        if not document.tables:
            raise MasterDataWriteError(
                f"No MASTER_DATA table found in {source_path.name}"
            )

        table = document.tables[0]
        row = table.add_row()

        row.cells[0].text = (
            _format_master_date(
                draw_date
            )
        )

        row.cells[1].text = "-".join(
            str(number)
            for number in numbers
        )

        _atomic_save_document(
            document,
            source_path,
        )

        rows_after = _existing_rows(
            source_path
        )

        if (
            len(rows_after)
            != count_before + 1
        ):
            raise MasterDataWriteError(
                "Post-write verification failed: row count did not "
                "increase by exactly one."
            )

        expected_date = draw_date
        expected_numbers = tuple(
            numbers
        )

        occurrences = 0

        for date_text, draw_text in rows_after:
            existing_date = (
                _parse_existing_date(
                    date_text
                )
            )

            existing_numbers = (
                _parse_existing_numbers(
                    draw_text
                )
            )

            if (
                existing_date
                == expected_date
                and existing_numbers
                == expected_numbers
            ):
                occurrences += 1

        if occurrences != 1:
            raise MasterDataWriteError(
                "Post-write verification failed: the new draw was "
                "not found exactly once."
            )

        return {
            "status": "success",
            "game": source_path.stem,
            "date": draw_date.isoformat(),
            "numbers": numbers,
            "source_file": str(
                source_path
            ),
            "rows_before": count_before,
            "rows_after": len(
                rows_after
            ),
            "backup_file": str(
                backup_path
            ),
        }

    except Exception:
        shutil.copy2(
            backup_path,
            source_path,
        )
        raise