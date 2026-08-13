from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterator, Mapping, Sequence


# ============================================================
# TOC PHASE 3 — ENGINE DATA SERVICE
# ============================================================
#
# PURPOSE
# -------
# Permanent read-only gateway between:
#
#  normalized_master_data.json
#
# and all TOC analytical / intelligence engines.
#
# Engines should consume THIS SERVICE rather than:
#  - reading MASTER_DATA DOCX files
#  - parsing JSON independently
#  - depending on normalized JSON implementation details
#
# DESIGN PRINCIPLES
# -----------------
# - strict schema validation
# - canonical SHA-256 verification
# - immutable engine-facing records
# - deterministic chronological ordering
# - indexed game/date lookup
# - case-insensitive game resolution
# - explicit typed exceptions
# - provenance preservation
# - defensive boundaries
# - automatic stale-file detection
# - thread-safe reload
# - no prediction logic
# - no source mutation
# ============================================================


EXPECTED_SCHEMA = "toc.normalized_master_data"
SUPPORTED_SCHEMA_VERSIONS = frozenset({1})
EXPECTED_GAME_COUNT = 19
DRAW_SIZE = 5

BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_PATH = (
    BACKEND_DIR
    / "data"
    / "normalized_master_data.json"
)


# ============================================================
# EXCEPTIONS
# ============================================================

class DataServiceError(Exception):
    """Base exception for the TOC engine data service."""


class DatasetNotFoundError(DataServiceError):
    """Canonical normalized dataset does not exist."""


class DatasetReadError(DataServiceError):
    """Canonical dataset cannot be read or decoded."""


class DatasetValidationError(DataServiceError):
    """Canonical dataset violates its required contract."""


class DatasetIntegrityError(DataServiceError):
    """Canonical dataset fingerprint does not verify."""


class UnsupportedSchemaError(DataServiceError):
    """Dataset schema/version is unsupported."""


class GameNotFoundError(DataServiceError):
    """Requested canonical game does not exist."""


class DrawNotFoundError(DataServiceError):
    """Requested draw/date does not exist for the game."""


# ============================================================
# IMMUTABLE ENGINE-FACING MODELS
# ============================================================

@dataclass(frozen=True, slots=True)
class DrawRecord:
    game: str
    draw_date: date
    draw_numbers: tuple[int, ...]
    source_file: str
    source_table: int
    source_row: int
    source_date_text: str
    source_draw_text: str

    @property
    def iso_date(self) -> str:
        return self.draw_date.isoformat()

    def numbers_list(self) -> list[int]:
        """
        Return a fresh mutable list when an engine specifically
        needs list semantics.
        """
        return list(self.draw_numbers)

    def as_dict(self) -> dict[str, Any]:
        """
        Return a defensive plain-Python representation.
        """
        return {
            "game": self.game,
            "draw_date": self.iso_date,
            "draw_numbers": list(self.draw_numbers),
            "source_file": self.source_file,
            "source_table": self.source_table,
            "source_row": self.source_row,
            "source_date_text": self.source_date_text,
            "source_draw_text": self.source_draw_text,
        }


@dataclass(frozen=True, slots=True)
class GameInfo:
    name: str
    source_file: str
    source_sha256: str
    record_count: int
    first_draw_date: date
    latest_draw_date: date

    @property
    def first_draw_iso(self) -> str:
        return self.first_draw_date.isoformat()

    @property
    def latest_draw_iso(self) -> str:
        return self.latest_draw_date.isoformat()

    def as_dict(self) -> dict[str, Any]:
        return {
            "game": self.name,
            "source_file": self.source_file,
            "source_sha256": self.source_sha256,
            "record_count": self.record_count,
            "first_draw_date": self.first_draw_iso,
            "latest_draw_date": self.latest_draw_iso,
        }


@dataclass(frozen=True, slots=True)
class DatasetInfo:
    schema: str
    schema_version: int
    generated_at_utc: str
    game_count: int
    record_count: int
    dataset_sha256: str
    data_path: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "generated_at_utc": self.generated_at_utc,
            "game_count": self.game_count,
            "record_count": self.record_count,
            "dataset_sha256": self.dataset_sha256,
            "data_path": self.data_path,
        }


# ============================================================
# INTERNAL IMMUTABLE SNAPSHOT
# ============================================================

@dataclass(frozen=True, slots=True)
class _Snapshot:
    info: DatasetInfo
    games: tuple[str, ...]
    game_lookup: Mapping[str, str]
    records_by_game: Mapping[str, tuple[DrawRecord, ...]]
    records_by_date: Mapping[
        str,
        Mapping[date, DrawRecord],
    ]
    game_info: Mapping[str, GameInfo]
    file_signature: tuple[int, int]


# ============================================================
# VALIDATION HELPERS
# ============================================================

def _require_dict(
    value: Any,
    location: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DatasetValidationError(
            f"{location} must be an object"
        )
    return value


def _require_list(
    value: Any,
    location: str,
) -> list[Any]:
    if not isinstance(value, list):
        raise DatasetValidationError(
            f"{location} must be an array"
        )
    return value


def _require_string(
    value: Any,
    location: str,
    *,
    nonempty: bool = True,
) -> str:
    if not isinstance(value, str):
        raise DatasetValidationError(
            f"{location} must be a string"
        )

    if nonempty and not value.strip():
        raise DatasetValidationError(
            f"{location} must not be empty"
        )

    return value


def _require_int(
    value: Any,
    location: str,
    *,
    minimum: int | None = None,
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
    ):
        raise DatasetValidationError(
            f"{location} must be an integer"
        )

    if minimum is not None and value < minimum:
        raise DatasetValidationError(
            f"{location} must be >= {minimum}"
        )

    return value


def _validate_sha256(
    value: Any,
    location: str,
) -> str:
    text = _require_string(
        value,
        location,
    )

    if len(text) != 64:
        raise DatasetValidationError(
            f"{location} is not a 64-character SHA-256"
        )

    try:
        int(text, 16)
    except ValueError as exc:
        raise DatasetValidationError(
            f"{location} is not hexadecimal"
        ) from exc

    return text.lower()


def _parse_iso_date(
    value: Any,
    location: str,
) -> date:
    text = _require_string(
        value,
        location,
    )

    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise DatasetValidationError(
            f"{location} is not a valid ISO date: "
            f"{text!r}"
        ) from exc


def _validate_generated_at(
    value: Any,
) -> str:
    text = _require_string(
        value,
        "generated_at_utc",
    )

    try:
        datetime.fromisoformat(text)
    except ValueError as exc:
        raise DatasetValidationError(
            "generated_at_utc is not valid ISO datetime"
        ) from exc

    return text


# ============================================================
# CANONICAL HASH VERIFICATION
# ============================================================

def _canonical_payload(
    dataset: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Must mirror normalized_data.py's canonical hash contract.
    """

    return {
        "schema": dataset["schema"],
        "schema_version": dataset["schema_version"],
        "game_count": dataset["game_count"],
        "record_count": dataset["record_count"],
        "games": dataset["games"],
    }


def _calculate_dataset_sha256(
    dataset: Mapping[str, Any],
) -> str:
    encoded = json.dumps(
        _canonical_payload(dataset),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


# ============================================================
# DATA SERVICE
# ============================================================

class EngineDataService:
    """
    Thread-safe, read-only TOC canonical data gateway.

    The complete dataset is validated before a new snapshot
    becomes visible to callers.

    A changed JSON file is automatically detected using file
    modification time + size and reloaded atomically.
    """

    def __init__(
        self,
        data_path: str | Path | None = None,
        *,
        auto_reload: bool = True,
    ) -> None:

        self._data_path = Path(
            data_path
            if data_path is not None
            else DEFAULT_DATA_PATH
        ).expanduser().resolve()

        self._auto_reload = bool(auto_reload)
        self._lock = threading.RLock()
        self._snapshot: _Snapshot | None = None

        self.reload(force=True)


    # --------------------------------------------------------
    # INTERNAL FILE HANDLING
    # --------------------------------------------------------

    def _file_signature(self) -> tuple[int, int]:
        try:
            stat = self._data_path.stat()
        except FileNotFoundError as exc:
            raise DatasetNotFoundError(
                f"Canonical dataset not found: "
                f"{self._data_path}"
            ) from exc
        except OSError as exc:
            raise DatasetReadError(
                f"Cannot stat canonical dataset: "
                f"{self._data_path}: {exc}"
            ) from exc

        if not self._data_path.is_file():
            raise DatasetNotFoundError(
                f"Canonical dataset is not a file: "
                f"{self._data_path}"
            )

        return (
            stat.st_mtime_ns,
            stat.st_size,
        )


    def _read_json(self) -> dict[str, Any]:
        try:
            with self._data_path.open(
                "r",
                encoding="utf-8",
            ) as handle:
                payload = json.load(handle)

        except FileNotFoundError as exc:
            raise DatasetNotFoundError(
                f"Canonical dataset not found: "
                f"{self._data_path}"
            ) from exc

        except json.JSONDecodeError as exc:
            raise DatasetReadError(
                "Canonical dataset contains invalid JSON: "
                f"line {exc.lineno}, column {exc.colno}: "
                f"{exc.msg}"
            ) from exc

        except (OSError, UnicodeError) as exc:
            raise DatasetReadError(
                f"Cannot read canonical dataset: {exc}"
            ) from exc

        return _require_dict(
            payload,
            "dataset root",
        )


    # --------------------------------------------------------
    # SNAPSHOT BUILD
    # --------------------------------------------------------

    def _build_snapshot(
        self,
        dataset: dict[str, Any],
        signature: tuple[int, int],
    ) -> _Snapshot:

        schema = _require_string(
            dataset.get("schema"),
            "schema",
        )

        if schema != EXPECTED_SCHEMA:
            raise UnsupportedSchemaError(
                f"Unsupported schema {schema!r}; "
                f"expected {EXPECTED_SCHEMA!r}"
            )

        schema_version = _require_int(
            dataset.get("schema_version"),
            "schema_version",
            minimum=1,
        )

        if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise UnsupportedSchemaError(
                f"Unsupported schema version "
                f"{schema_version}; supported versions: "
                f"{sorted(SUPPORTED_SCHEMA_VERSIONS)}"
            )

        generated_at = _validate_generated_at(
            dataset.get("generated_at_utc")
        )

        declared_game_count = _require_int(
            dataset.get("game_count"),
            "game_count",
            minimum=1,
        )

        if declared_game_count != EXPECTED_GAME_COUNT:
            raise DatasetValidationError(
                f"Expected {EXPECTED_GAME_COUNT} games; "
                f"dataset declares {declared_game_count}"
            )

        declared_record_count = _require_int(
            dataset.get("record_count"),
            "record_count",
            minimum=1,
        )

        declared_hash = _validate_sha256(
            dataset.get("dataset_sha256"),
            "dataset_sha256",
        )

        actual_hash = _calculate_dataset_sha256(
            dataset
        )

        if actual_hash != declared_hash:
            raise DatasetIntegrityError(
                "Canonical dataset SHA-256 verification "
                "failed"
            )

        raw_games = _require_list(
            dataset.get("games"),
            "games",
        )

        if len(raw_games) != declared_game_count:
            raise DatasetValidationError(
                "game_count does not match games array "
                f"length: {declared_game_count} != "
                f"{len(raw_games)}"
            )

        game_names: list[str] = []
        game_lookup: dict[str, str] = {}
        records_by_game: dict[
            str,
            tuple[DrawRecord, ...],
        ] = {}
        records_by_date: dict[
            str,
            Mapping[date, DrawRecord],
        ] = {}
        game_info_map: dict[str, GameInfo] = {}

        calculated_total = 0

        for game_index, raw_game_value in enumerate(
            raw_games
        ):
            location = f"games[{game_index}]"

            raw_game = _require_dict(
                raw_game_value,
                location,
            )

            game_name = _require_string(
                raw_game.get("game"),
                f"{location}.game",
            ).strip()

            lookup_key = game_name.casefold()

            if lookup_key in game_lookup:
                raise DatasetValidationError(
                    f"Duplicate game name: {game_name!r}"
                )

            source = _require_dict(
                raw_game.get("source"),
                f"{location}.source",
            )

            source_file = _require_string(
                source.get("file"),
                f"{location}.source.file",
            )

            if not source_file.lower().endswith(".docx"):
                raise DatasetValidationError(
                    f"{location}.source.file must be "
                    "a DOCX filename"
                )

            source_sha256 = _validate_sha256(
                source.get("sha256"),
                f"{location}.source.sha256",
            )

            declared_game_records = _require_int(
                raw_game.get("record_count"),
                f"{location}.record_count",
                minimum=1,
            )

            raw_records = _require_list(
                raw_game.get("records"),
                f"{location}.records",
            )

            if (
                len(raw_records)
                != declared_game_records
            ):
                raise DatasetValidationError(
                    f"{game_name}: declared "
                    f"{declared_game_records} records but "
                    f"contains {len(raw_records)}"
                )

            parsed_records: list[DrawRecord] = []
            date_index: dict[date, DrawRecord] = {}

            for record_index, raw_record_value in enumerate(
                raw_records
            ):
                record_location = (
                    f"{location}.records[{record_index}]"
                )

                raw_record = _require_dict(
                    raw_record_value,
                    record_location,
                )

                record_game = _require_string(
                    raw_record.get("game"),
                    f"{record_location}.game",
                )

                if record_game != game_name:
                    raise DatasetValidationError(
                        f"{record_location}.game "
                        f"{record_game!r} does not match "
                        f"parent game {game_name!r}"
                    )

                record_source_file = _require_string(
                    raw_record.get("source_file"),
                    f"{record_location}.source_file",
                )

                if record_source_file != source_file:
                    raise DatasetValidationError(
                        f"{record_location}.source_file "
                        "does not match parent source file"
                    )

                source_table = _require_int(
                    raw_record.get("source_table"),
                    f"{record_location}.source_table",
                    minimum=1,
                )

                source_row = _require_int(
                    raw_record.get("source_row"),
                    f"{record_location}.source_row",
                    minimum=2,
                )

                source_date_text = _require_string(
                    raw_record.get(
                        "source_date_text"
                    ),
                    (
                        f"{record_location}."
                        "source_date_text"
                    ),
                )

                source_draw_text = _require_string(
                    raw_record.get(
                        "source_draw_text"
                    ),
                    (
                        f"{record_location}."
                        "source_draw_text"
                    ),
                )

                draw_date = _parse_iso_date(
                    raw_record.get("draw_date"),
                    f"{record_location}.draw_date",
                )

                raw_numbers = _require_list(
                    raw_record.get("draw_numbers"),
                    f"{record_location}.draw_numbers",
                )

                if len(raw_numbers) != DRAW_SIZE:
                    raise DatasetValidationError(
                        f"{record_location}.draw_numbers "
                        f"must contain exactly "
                        f"{DRAW_SIZE} numbers"
                    )

                numbers: list[int] = []

                for number_index, value in enumerate(
                    raw_numbers
                ):
                    number = _require_int(
                        value,
                        (
                            f"{record_location}."
                            f"draw_numbers[{number_index}]"
                        ),
                    )

                    numbers.append(number)

                record = DrawRecord(
                    game=game_name,
                    draw_date=draw_date,
                    draw_numbers=tuple(numbers),
                    source_file=record_source_file,
                    source_table=source_table,
                    source_row=source_row,
                    source_date_text=source_date_text,
                    source_draw_text=source_draw_text,
                )

                if draw_date in date_index:
                    previous = date_index[draw_date]

                    raise DatasetValidationError(
                        f"{game_name}: multiple canonical "
                        f"records exist for "
                        f"{draw_date.isoformat()}; "
                        f"source rows "
                        f"{previous.source_row} and "
                        f"{source_row}"
                    )

                date_index[draw_date] = record
                parsed_records.append(record)

            # Source row order is provenance only.
            # Canonical date is the engine ordering authority.
            parsed_records.sort(
                key=lambda record: (
                    record.draw_date,
                    record.source_table,
                    record.source_row,
                )
            )

            immutable_records = tuple(
                parsed_records
            )

            if not immutable_records:
                raise DatasetValidationError(
                    f"{game_name}: no records"
                )

            info = GameInfo(
                name=game_name,
                source_file=source_file,
                source_sha256=source_sha256,
                record_count=len(
                    immutable_records
                ),
                first_draw_date=(
                    immutable_records[0].draw_date
                ),
                latest_draw_date=(
                    immutable_records[-1].draw_date
                ),
            )

            game_names.append(game_name)
            game_lookup[lookup_key] = game_name
            records_by_game[game_name] = (
                immutable_records
            )
            records_by_date[game_name] = (
                MappingProxyType(date_index)
            )
            game_info_map[game_name] = info

            calculated_total += len(
                immutable_records
            )

        if calculated_total != declared_record_count:
            raise DatasetValidationError(
                "record_count mismatch: dataset declares "
                f"{declared_record_count}, calculated "
                f"{calculated_total}"
            )

        # Preserve canonical game ordering from the dataset.
        immutable_games = tuple(game_names)

        dataset_info = DatasetInfo(
            schema=schema,
            schema_version=schema_version,
            generated_at_utc=generated_at,
            game_count=declared_game_count,
            record_count=declared_record_count,
            dataset_sha256=declared_hash,
            data_path=str(self._data_path),
        )

        return _Snapshot(
            info=dataset_info,
            games=immutable_games,
            game_lookup=MappingProxyType(
                game_lookup
            ),
            records_by_game=MappingProxyType(
                records_by_game
            ),
            records_by_date=MappingProxyType(
                records_by_date
            ),
            game_info=MappingProxyType(
                game_info_map
            ),
            file_signature=signature,
        )


    # --------------------------------------------------------
    # SNAPSHOT MANAGEMENT
    # --------------------------------------------------------

    def reload(
        self,
        *,
        force: bool = False,
    ) -> bool:
        """
        Reload and fully validate the canonical dataset.

        Returns True when a new snapshot was installed.
        Returns False when the existing snapshot was current.

        A failed reload never destroys the last valid snapshot.
        """

        with self._lock:
            signature = self._file_signature()

            current = self._snapshot

            if (
                not force
                and current is not None
                and current.file_signature == signature
            ):
                return False

            dataset = self._read_json()

            # Build completely before replacing current state.
            new_snapshot = self._build_snapshot(
                dataset,
                signature,
            )

            self._snapshot = new_snapshot

            return True


    def _current(self) -> _Snapshot:
        if self._auto_reload:
            self.reload(force=False)

        snapshot = self._snapshot

        if snapshot is None:
            raise DataServiceError(
                "Data service has no valid snapshot"
            )

        return snapshot


    # --------------------------------------------------------
    # GAME RESOLUTION
    # --------------------------------------------------------

    def _resolve_game(
        self,
        game: str,
        snapshot: _Snapshot,
    ) -> str:

        if not isinstance(game, str):
            raise TypeError(
                "game must be a string"
            )

        key = game.strip().casefold()

        if not key:
            raise GameNotFoundError(
                "Game name must not be empty"
            )

        canonical = snapshot.game_lookup.get(key)

        if canonical is None:
            available = ", ".join(snapshot.games)

            raise GameNotFoundError(
                f"Unknown game {game!r}. "
                f"Available games: {available}"
            )

        return canonical


    # --------------------------------------------------------
    # DATASET METADATA
    # --------------------------------------------------------

    @property
    def data_path(self) -> Path:
        return self._data_path


    @property
    def auto_reload(self) -> bool:
        return self._auto_reload


    def dataset_info(self) -> DatasetInfo:
        return self._current().info


    def dataset_sha256(self) -> str:
        return self._current().info.dataset_sha256


    def game_count(self) -> int:
        return self._current().info.game_count


    def total_record_count(self) -> int:
        return self._current().info.record_count


    # --------------------------------------------------------
    # GAME DISCOVERY
    # --------------------------------------------------------

    def games(self) -> tuple[str, ...]:
        """
        Return all canonical game names.
        """
        return self._current().games


    def has_game(self, game: str) -> bool:
        if not isinstance(game, str):
            return False

        key = game.strip().casefold()

        if not key:
            return False

        return key in self._current().game_lookup


    def canonical_game_name(
        self,
        game: str,
    ) -> str:
        snapshot = self._current()

        return self._resolve_game(
            game,
            snapshot,
        )


    def game_info(
        self,
        game: str,
    ) -> GameInfo:
        snapshot = self._current()

        canonical = self._resolve_game(
            game,
            snapshot,
        )

        return snapshot.game_info[canonical]


    def all_game_info(
        self,
    ) -> tuple[GameInfo, ...]:
        snapshot = self._current()

        return tuple(
            snapshot.game_info[name]
            for name in snapshot.games
        )


    # --------------------------------------------------------
    # RECORD ACCESS
    # --------------------------------------------------------

    def records(
        self,
        game: str,
    ) -> tuple[DrawRecord, ...]:
        """
        Return complete chronological history for one game.

        The returned tuple and DrawRecord objects are immutable.
        """
        snapshot = self._current()

        canonical = self._resolve_game(
            game,
            snapshot,
        )

        return snapshot.records_by_game[
            canonical
        ]


    def record_count(
        self,
        game: str,
    ) -> int:
        return self.game_info(game).record_count


    def latest(
        self,
        game: str,
    ) -> DrawRecord:
        records = self.records(game)

        if not records:
            raise DrawNotFoundError(
                f"No draws available for {game!r}"
            )

        return records[-1]


    def earliest(
        self,
        game: str,
    ) -> DrawRecord:
        records = self.records(game)

        if not records:
            raise DrawNotFoundError(
                f"No draws available for {game!r}"
            )

        return records[0]


    def by_date(
        self,
        game: str,
        draw_date: date | str,
    ) -> DrawRecord:
        snapshot = self._current()

        canonical = self._resolve_game(
            game,
            snapshot,
        )

        if isinstance(draw_date, str):
            try:
                target = date.fromisoformat(
                    draw_date
                )
            except ValueError as exc:
                raise ValueError(
                    "draw_date string must use "
                    "YYYY-MM-DD format"
                ) from exc

        elif isinstance(draw_date, date):
            target = draw_date

        else:
            raise TypeError(
                "draw_date must be datetime.date "
                "or ISO date string"
            )

        record = snapshot.records_by_date[
            canonical
        ].get(target)

        if record is None:
            raise DrawNotFoundError(
                f"No {canonical!r} draw exists for "
                f"{target.isoformat()}"
            )

        return record


    # --------------------------------------------------------
    # CHRONOLOGICAL WINDOWS
    # --------------------------------------------------------

    def history(
        self,
        game: str,
        *,
        limit: int | None = None,
        newest_first: bool = False,
    ) -> tuple[DrawRecord, ...]:
        """
        Retrieve game history.

        limit=None:
            all records.

        limit=N:
            most recent N records.

        newest_first controls returned presentation order.
        """

        records = self.records(game)

        if limit is not None:
            if (
                not isinstance(limit, int)
                or isinstance(limit, bool)
                or limit < 1
            ):
                raise ValueError(
                    "limit must be a positive integer "
                    "or None"
                )

            selected = records[-limit:]
        else:
            selected = records

        if newest_first:
            return tuple(reversed(selected))

        return selected


    def between(
        self,
        game: str,
        start: date | str,
        end: date | str,
    ) -> tuple[DrawRecord, ...]:
        """
        Inclusive chronological date-range query.
        """

        start_date = self._coerce_date(
            start,
            "start",
        )

        end_date = self._coerce_date(
            end,
            "end",
        )

        if start_date > end_date:
            raise ValueError(
                "start date must not be after end date"
            )

        return tuple(
            record
            for record in self.records(game)
            if start_date
            <= record.draw_date
            <= end_date
        )


    @staticmethod
    def _coerce_date(
        value: date | str,
        field_name: str,
    ) -> date:

        if isinstance(value, date):
            return value

        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(
                    f"{field_name} must use "
                    "YYYY-MM-DD format"
                ) from exc

        raise TypeError(
            f"{field_name} must be datetime.date "
            "or ISO date string"
        )


    # --------------------------------------------------------
    # ENGINE-READY VIEWS
    # --------------------------------------------------------

    def dates(
        self,
        game: str,
    ) -> tuple[date, ...]:
        return tuple(
            record.draw_date
            for record in self.records(game)
        )


    def iso_dates(
        self,
        game: str,
    ) -> tuple[str, ...]:
        return tuple(
            record.iso_date
            for record in self.records(game)
        )


    def draws(
        self,
        game: str,
    ) -> tuple[tuple[int, ...], ...]:
        """
        Immutable chronological matrix of draw numbers.
        """
        return tuple(
            record.draw_numbers
            for record in self.records(game)
        )


    def draws_as_lists(
        self,
        game: str,
    ) -> list[list[int]]:
        """
        Fresh mutable 2-D list for engines/libraries that
        require list input.
        """
        return [
            list(record.draw_numbers)
            for record in self.records(game)
        ]


    def dated_draws(
        self,
        game: str,
    ) -> tuple[
        tuple[date, tuple[int, ...]],
        ...
    ]:
        return tuple(
            (
                record.draw_date,
                record.draw_numbers,
            )
            for record in self.records(game)
        )


    def engine_payload(
        self,
        game: str,
        *,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """
        Stable plain-Python boundary for analytical engines.

        This intentionally hides the normalized JSON's physical
        nesting from downstream engines.
        """

        snapshot = self._current()

        canonical = self._resolve_game(
            game,
            snapshot,
        )

        info = snapshot.game_info[canonical]

        records = self.history(
            canonical,
            limit=limit,
        )

        return {
            "game": canonical,
            "record_count": len(records),
            "total_available_records": (
                info.record_count
            ),
            "first_draw_date": (
                records[0].iso_date
                if records
                else None
            ),
            "latest_draw_date": (
                records[-1].iso_date
                if records
                else None
            ),
            "dates": [
                record.iso_date
                for record in records
            ],
            "draws": [
                list(record.draw_numbers)
                for record in records
            ],
            "dataset": {
                "schema": snapshot.info.schema,
                "schema_version": (
                    snapshot.info.schema_version
                ),
                "dataset_sha256": (
                    snapshot.info.dataset_sha256
                ),
            },
        }


    # --------------------------------------------------------
    # PROVENANCE
    # --------------------------------------------------------

    def provenance(
        self,
        game: str,
        draw_date: date | str,
    ) -> dict[str, Any]:
        record = self.by_date(
            game,
            draw_date,
        )

        info = self.game_info(
            record.game
        )

        return {
            "game": record.game,
            "draw_date": record.iso_date,
            "draw_numbers": list(
                record.draw_numbers
            ),
            "source_file": record.source_file,
            "source_file_sha256": (
                info.source_sha256
            ),
            "source_table": record.source_table,
            "source_row": record.source_row,
            "source_date_text": (
                record.source_date_text
            ),
            "source_draw_text": (
                record.source_draw_text
            ),
        }


    # --------------------------------------------------------
    # ITERATION
    # --------------------------------------------------------

    def iter_game(
        self,
        game: str,
    ) -> Iterator[DrawRecord]:
        yield from self.records(game)


    def iter_all(
        self,
    ) -> Iterator[DrawRecord]:
        snapshot = self._current()

        for game in snapshot.games:
            yield from snapshot.records_by_game[
                game
            ]


    # --------------------------------------------------------
    # SERVICE HEALTH
    # --------------------------------------------------------

    def health_check(
        self,
    ) -> dict[str, Any]:
        """
        Force validation of the on-disk canonical dataset and
        return compact service status.
        """

        self.reload(force=True)

        snapshot = self._current()

        return {
            "status": "ok",
            "schema": snapshot.info.schema,
            "schema_version": (
                snapshot.info.schema_version
            ),
            "game_count": (
                snapshot.info.game_count
            ),
            "record_count": (
                snapshot.info.record_count
            ),
            "dataset_sha256": (
                snapshot.info.dataset_sha256
            ),
            "data_path": (
                snapshot.info.data_path
            ),
        }


# ============================================================
# DEFAULT APPLICATION SERVICE
# ============================================================

_default_service: EngineDataService | None = None
_default_service_lock = threading.Lock()


def get_data_service() -> EngineDataService:
    """
    Return the process-wide default data service.

    Engines may import this function instead of constructing
    their own service instances.
    """

    global _default_service

    if _default_service is None:
        with _default_service_lock:
            if _default_service is None:
                _default_service = (
                    EngineDataService()
                )

    return _default_service


# ============================================================
# COMMAND-LINE SELF TEST
# ============================================================

def main() -> int:
    try:
        service = EngineDataService()

        health = service.health_check()

        print()
        print(
            "=== TOC ENGINE DATA SERVICE ==="
        )

        print(
            f"Schema:          "
            f"{health['schema']}"
        )

        print(
            f"Schema version:  "
            f"{health['schema_version']}"
        )

        print(
            f"Games:          "
            f"{health['game_count']}"
        )

        print(
            f"Records:        "
            f"{health['record_count']}"
        )

        print(
            f"Dataset SHA-256: "
            f"{health['dataset_sha256']}"
        )

        print()
        print("=== GAME COVERAGE ===")

        for info in service.all_game_info():
            print(
                f"{info.name}: "
                f"{info.record_count} records | "
                f"{info.first_draw_iso} -> "
                f"{info.latest_draw_iso}"
            )

        print()
        print(
            "SCHEMA VALIDATION: PASSED"
        )
        print(
            "DATASET SHA-256: PASSED"
        )
        print(
            "GAME INDEX: PASSED"
        )
        print(
            "DATE INDEX: PASSED"
        )
        print(
            "ENGINE DATA SERVICE: PASSED"
        )

        return 0

    except DataServiceError as exc:
        print()
        print(
            "ENGINE DATA SERVICE: FAILED"
        )
        print(
            f"{type(exc).__name__}: {exc}"
        )
        return 2

    except Exception as exc:
        print()
        print(
            "ENGINE DATA SERVICE: FAILED"
        )
        print(
            f"{type(exc).__name__}: {exc}"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())