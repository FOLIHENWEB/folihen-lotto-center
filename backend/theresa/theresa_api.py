from __future__ import annotations

import json
import os
import runpy
import shutil
import subprocess
import sys
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from flask import Flask, jsonify, request

APP_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = APP_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from normalized_data import execute as execute_normalization
from master_data_writer import append_draw, MasterDataWriteError
from engine_data_service import DataServiceError, get_data_service

THERESA_DIR = BACKEND_DIR / "theresa"
THERESA_ENGINE = THERESA_DIR / "theresa_engine_toc.py"

KADIJA_ENGINE = (
    BACKEND_DIR
    / "engines"
    / "kadija"
    / "kadija_engine_toc.py"
)

DESMOND_ENGINE = (
    BACKEND_DIR
    / "engines"
    / "desmond"
    / "desmond_engine_toc.py"
)

DOCUMENTS = Path.home() / "Documents"

THERESA_OUTPUT_DIR = (
    DOCUMENTS
    / "Banger_Tracker"
    / "Theresa_Predictor"
    / "input_stream"
)

DEFAULT_TARGET_GAME = "vag friday"

app = Flask(__name__)

PREDICTION_LATEST_FILE = (
    BACKEND_DIR
    / "data"
    / "latest_prediction_engines.json"
)


def _save_latest_prediction_run(payload: dict) -> None:
    PREDICTION_LATEST_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = PREDICTION_LATEST_FILE.with_suffix(
        ".json.tmp"
    )

    temp_path.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    temp_path.replace(PREDICTION_LATEST_FILE)


def _engine_prediction_is_usable(result: Any) -> bool:
    if not isinstance(result, dict) or result.get("status") != "success":
        return False

    prediction = result.get("prediction")
    if not isinstance(prediction, dict):
        return False

    if not all(
        _prediction_number_list(prediction.get(field_name))
        for field_name in ("top5", "top2")
    ):
        return False

    try:
        int(prediction.get("banker"))
    except (TypeError, ValueError):
        return False

    confidence = prediction.get("confidence")
    return (
        isinstance(confidence, (int, float))
        and not isinstance(confidence, bool)
    )


def _prediction_run_is_usable(payload: Any) -> bool:
    if not isinstance(payload, dict) or payload.get("status") != "success":
        return False

    results = payload.get("results")
    return (
        isinstance(results, list)
        and len(results) == 2
        and all(_engine_prediction_is_usable(result) for result in results)
    )


def _iso_mtime(path: Path) -> str:
    return datetime.fromtimestamp(
        path.stat().st_mtime,
        tz=timezone.utc,
    ).isoformat()


def _read_json_file(path: Path) -> Optional[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    return data if isinstance(data, dict) else None


def _persisted_prediction_run() -> Optional[dict[str, Any]]:
    if not PREDICTION_LATEST_FILE.is_file():
        return None

    payload = _read_json_file(PREDICTION_LATEST_FILE)
    return payload if _prediction_run_is_usable(payload) else None


def _theresa_history_entries() -> list[dict[str, Any]]:
    if not THERESA_OUTPUT_DIR.is_dir():
        return []

    entries: list[dict[str, Any]] = []
    for path in THERESA_OUTPUT_DIR.glob("Theresa_*.json"):
        prediction = _read_json_file(path)
        if prediction is None:
            continue

        entries.append(
            {
                "id": str(path),
                "timestamp": (
                    prediction.get("generated")
                    or prediction.get("prediction_date")
                    or _iso_mtime(path)
                ),
                "game": prediction.get("game") or prediction.get("target_game"),
                "operation": "Theresa",
                "source": "Theresa",
                "status": "success",
                "summary": "Persisted Theresa prediction output.",
                "artifact": str(path),
                "prediction": prediction,
            }
        )

    return entries


def _operation_history() -> list[dict[str, Any]]:
    entries = _theresa_history_entries()
    prediction_run = _persisted_prediction_run()

    if prediction_run is not None:
        entries.append(
            {
                "id": str(PREDICTION_LATEST_FILE),
                "timestamp": _iso_mtime(PREDICTION_LATEST_FILE),
                "game": prediction_run.get("game"),
                "operation": "Prediction Engines",
                "source": "Kadija + Desmond",
                "status": prediction_run.get("status"),
                "summary": prediction_run.get("message"),
                "artifact": str(PREDICTION_LATEST_FILE),
                "results": prediction_run.get("results", []),
            }
        )

    return sorted(
        entries,
        key=lambda entry: str(entry.get("timestamp") or ""),
        reverse=True,
    )


@app.get("/api/prediction-engines/latest")
def prediction_engines_latest():
    if not PREDICTION_LATEST_FILE.is_file():
        return (
            jsonify(
                {
                    "status": "not_found",
                    "message": (
                        "No saved prediction-engine "
                        "run is available yet."
                    ),
                }
            ),
            404,
        )

    try:
        payload = json.loads(
            PREDICTION_LATEST_FILE.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": (
                        "Latest prediction-engine "
                        "result could not be read."
                    ),
                    "detail": str(exc),
                }
            ),
            500,
        )

    if not _prediction_run_is_usable(payload):
        return (
            jsonify(
                {
                    "status": "not_found",
                    "message": (
                        "The saved prediction-engine result is incomplete "
                        "and cannot be displayed as a successful run."
                    ),
                }
            ),
            404,
        )

    return jsonify(payload), 200

def normalize_game_name(value: str) -> str:
    return " ".join(
        str(value)
        .lower()
        .strip()
        .replace("_", " ")
        .replace("-", " ")
        .split()
    )


def latest_theresa_prediction(
    target_game: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if not THERESA_OUTPUT_DIR.exists():
        return None

    files = sorted(
        THERESA_OUTPUT_DIR.glob("Theresa_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    target_norm = (
        normalize_game_name(target_game)
        if target_game
        else None
    )

    for path in files:
        try:
            data = json.loads(
                path.read_text(encoding="utf-8")
            )
        except Exception:
            continue

        if target_norm:
            game = normalize_game_name(
                data.get("game", "")
            )
            if game != target_norm:
                continue

        data["_source_file"] = str(path)
        return data

    return None


def run_theresa(
    target_game: str,
    source_mode: str = "auto",
    lookback: int = 0,
    trigger_depth: int = 3,
    min_consistency: int = 2,
) -> Dict[str, Any]:
    if not THERESA_ENGINE.exists():
        raise FileNotFoundError(
            f"Theresa engine not found: {THERESA_ENGINE}"
        )

    target_game = normalize_game_name(target_game)

    cmd = [
        sys.executable,
        str(THERESA_ENGINE),
        "--target",
        target_game,
        "--source-mode",
        source_mode,
        "--lookback",
        str(int(lookback)),
        "--trigger-depth",
        str(int(trigger_depth)),
        "--min-consistency",
        str(int(min_consistency)),
    ]

    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND_DIR)

    completed = subprocess.run(
        cmd,
        cwd=str(APP_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            "Theresa execution failed.\n"
            f"STDOUT:\n{completed.stdout}\n"
            f"STDERR:\n{completed.stderr}"
        )

    prediction = latest_theresa_prediction(target_game)

    if prediction is None:
        raise RuntimeError(
            "Theresa completed but no prediction JSON was found."
        )

    return {
        "status": "success",
        "target_game": target_game,
        "prediction": prediction,
        "stdout": completed.stdout,
    }


def _resolve_kadija_game_id(game_name: str) -> int:
    if not KADIJA_ENGINE.exists():
        raise RuntimeError(
            f"Kadija engine not found: {KADIJA_ENGINE}"
        )

    namespace = runpy.run_path(str(KADIJA_ENGINE))
    resolver = namespace.get("get_game_id")

    if not callable(resolver):
        raise RuntimeError(
            "Kadija get_game_id() function was not found."
        )

    game_id = resolver(game_name)

    if game_id is None:
        raise RuntimeError(
            f"Unknown prediction game: {game_name}"
        )

    return int(game_id)


def _canonical_game_name(game_name: str) -> str:
    if not isinstance(game_name, str) or not game_name.strip():
        raise ValueError("A game must be selected.")

    return get_data_service().canonical_game_name(game_name)


def _run_prediction_engine(
    *,
    engine_name: str,
    script_path: Path,
    game_name: str,
    game_id: int,
) -> dict:
    if not script_path.exists():
        return {
            "engine": engine_name,
            "status": "error",
            "message": (
                f"Engine file not found: {script_path}"
            ),
        }

    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND_DIR)
    env["RUN_TYPE"] = "prediction"

    if engine_name.lower() == "desmond":
        command = [
            sys.executable,
            str(script_path),
            "--game",
            game_name,
        ]
        run_kwargs: dict[str, Any] = {}
    else:
        command = [
            sys.executable,
            str(script_path),
        ]
        run_kwargs = {"input": f"{game_id}\n"}

    try:
        completed = subprocess.run(
            command,
            cwd=str(BACKEND_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
            **run_kwargs,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "engine": engine_name,
            "status": "error",
            "message": "Engine execution timed out after 600 seconds.",
            "return_code": None,
            "stdout": (exc.stdout or "").strip(),
            "stderr": (exc.stderr or "").strip(),
        }
    except OSError as exc:
        return {
            "engine": engine_name,
            "status": "error",
            "message": f"Engine process could not be started: {exc}",
            "return_code": None,
            "stdout": "",
            "stderr": "",
        }

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()

    if completed.returncode != 0:
        return {
            "engine": engine_name,
            "status": "error",
            "message": "Engine exited with a non-zero status.",
            "return_code": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }

    return {
        "engine": engine_name,
        "status": "success",
        "return_code": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }


def _normalize_numbers_payload(
    raw_numbers: Any,
) -> list[int]:
    if not isinstance(raw_numbers, list):
        raise MasterDataWriteError(
            "numbers must be an array of five integers."
        )

    try:
        return [int(value) for value in raw_numbers]
    except (TypeError, ValueError) as exc:
        raise MasterDataWriteError(
            "numbers must contain integers only."
        ) from exc


@app.get("/api/theresa/health")
def theresa_health():
    return jsonify(
        {
            "status": "ok",
            "engine_exists": THERESA_ENGINE.exists(),
            "engine_path": str(THERESA_ENGINE),
            "output_dir": str(THERESA_OUTPUT_DIR),
            "output_dir_exists": THERESA_OUTPUT_DIR.exists(),
        }
    )


@app.get("/api/theresa/latest")
def theresa_latest():
    target_game = request.args.get("game")

    prediction = latest_theresa_prediction(target_game)

    if prediction is None:
        return (
            jsonify(
                {
                    "status": "not_found",
                    "message": "No Theresa prediction found.",
                }
            ),
            404,
        )

    return jsonify(
        {
            "status": "success",
            "prediction": prediction,
        }
    )


@app.get("/api/master-data/games")
def master_data_games():
    try:
        payload = [
            {
                "game": game,
            }
            for game in get_data_service().games()
        ]

        return jsonify(
            {
                "status": "success",
                "games": payload,
            }
        )
    except DataServiceError as exc:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"Canonical MASTER_DATA is unavailable: {exc}",
                }
            ),
            500,
        )


@app.get("/api/master-data/summary")
def master_data_summary():
    try:
        service = get_data_service()
        return jsonify(
            {
                "status": "success",
                "dataset": service.dataset_info().as_dict(),
                "games": [
                    game_info.as_dict()
                    for game_info in service.all_game_info()
                ],
            }
        )
    except DataServiceError as exc:
        return jsonify(
            {
                "status": "error",
                "message": f"Canonical MASTER_DATA is unavailable: {exc}",
            }
        ), 500


@app.get("/api/master-data/games/<path:game_name>")
def master_data_game_detail(game_name: str):
    try:
        service = get_data_service()
        canonical_game = service.canonical_game_name(game_name)
        records = service.history(
            canonical_game,
            limit=10,
            newest_first=True,
        )
        return jsonify(
            {
                "status": "success",
                "game": service.game_info(canonical_game).as_dict(),
                "recent_records": [
                    record.as_dict()
                    for record in records
                ],
            }
        )
    except (DataServiceError, ValueError) as exc:
        return jsonify(
            {
                "status": "error",
                "message": str(exc),
            }
        ), 404


@app.get("/api/history")
def history():
    game_filter = request.args.get("game", "").strip()
    operation_filter = request.args.get("operation", "").strip()

    entries = _operation_history()
    if game_filter:
        normalized_game = normalize_game_name(game_filter)
        entries = [
            entry for entry in entries
            if normalize_game_name(str(entry.get("game") or ""))
            == normalized_game
        ]

    if operation_filter:
        entries = [
            entry for entry in entries
            if entry.get("operation") == operation_filter
        ]

    return jsonify(
        {
            "status": "success",
            "records": entries,
        }
    )


@app.get("/api/reports")
def reports():
    game_filter = request.args.get("game", "").strip()
    source_filter = request.args.get("source", "").strip()
    rows: list[dict[str, Any]] = []

    for entry in _operation_history():
        if entry.get("operation") == "Prediction Engines":
            for result in entry.get("results", []):
                if not isinstance(result, dict):
                    continue
                rows.append(
                    {
                        "timestamp": entry.get("timestamp"),
                        "game": entry.get("game"),
                        "source": result.get("engine"),
                        "status": result.get("status"),
                        "prediction": result.get("prediction", {}),
                        "artifact": result.get("prediction_artifact"),
                    }
                )
        elif entry.get("operation") == "Theresa":
            rows.append(
                {
                    "timestamp": entry.get("timestamp"),
                    "game": entry.get("game"),
                    "source": "Theresa",
                    "status": entry.get("status"),
                    "prediction": entry.get("prediction", {}),
                    "artifact": entry.get("artifact"),
                }
            )

    if game_filter:
        normalized_game = normalize_game_name(game_filter)
        rows = [
            row for row in rows
            if normalize_game_name(str(row.get("game") or ""))
            == normalized_game
        ]

    if source_filter:
        rows = [
            row for row in rows
            if row.get("source") == source_filter
        ]

    return jsonify(
        {
            "status": "success",
            "reports": rows,
        }
    )

@app.post("/api/master-data/update")
def update_master_data():
    try:
        return_code = execute_normalization(
            dry_run=False
        )

        if return_code != 0:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "MASTER_DATA normalization failed.",
                        "return_code": return_code,
                    }
                ),
                500,
            )

        return jsonify(
            {
                "status": "success",
                "message": "MASTER_DATA normalized successfully.",
                "return_code": return_code,
            }
        )

    except Exception as exc:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": str(exc),
                }
            ),
            500,
        )


@app.post("/api/master-data/add-draw")
def add_master_data_draw():
    payload = request.get_json(silent=True) or {}

    game = str(payload.get("game", "")).strip()
    draw_date = str(payload.get("date", "")).strip()

    try:
        numbers = _normalize_numbers_payload(
            payload.get("numbers")
        )

        write_result = append_draw(
            game_name=game,
            draw_date_value=draw_date,
            draw_numbers=numbers,
        )

        source_file = Path(
            write_result["source_file"]
        )
        backup_file = Path(
            write_result["backup_file"]
        )

        try:
            return_code = execute_normalization(
                dry_run=False
            )

            if return_code != 0:
                raise RuntimeError(
                    "MASTER_DATA normalization failed "
                    f"with return code {return_code}."
                )

        except Exception:
            if backup_file.exists():
                shutil.copy2(
                    backup_file,
                    source_file,
                )

            try:
                execute_normalization(
                    dry_run=False
                )
            except Exception:
                pass

            raise

        return jsonify(
            {
                "status": "success",
                "message": (
                    f"Draw added successfully for "
                    f"{write_result['game']} and "
                    "MASTER_DATA normalized."
                ),
                "draw": {
                    "game": write_result["game"],
                    "date": write_result["date"],
                    "numbers": write_result["numbers"],
                    "rows_before": write_result["rows_before"],
                    "rows_after": write_result["rows_after"],
                },
                "source_file": write_result["source_file"],
                "normalization_return_code": return_code,
            }
        )

    except MasterDataWriteError as exc:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": str(exc),
                }
            ),
            400,
        )

    except Exception as exc:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": str(exc),
                }
            ),
            500,
        )

def _prediction_number_list(value: Any) -> list[int]:
    """
    Convert a prediction value into a clean list of integers.

    Supports:
      [11, 76, 77]
      ["11", "76", "77"]
      "11 76 77"
      "11, 76, 77"
    """
    if value is None:
        return []

    if isinstance(value, (list, tuple)):
        numbers: list[int] = []

        for item in value:
            if isinstance(item, dict):
                item = item.get("number")

            try:
                numbers.append(int(item))
            except (TypeError, ValueError):
                continue

        return numbers

    if isinstance(value, str):
        return [
            int(number)
            for number in re.findall(r"\b\d{1,2}\b", value)
        ]

    return []


def _find_prediction_value(data: Any, names: set[str]) -> Any:
    """
    Recursively search a JSON object for any matching field name.
    This lets Kadija keep its existing JSON structure.
    """
    if isinstance(data, dict):
        for key, value in data.items():
            normalized_key = str(key).lower().replace("-", "").replace("_", "")

            if normalized_key in names:
                return value

        for value in data.values():
            found = _find_prediction_value(value, names)

            if found is not None:
                return found

    elif isinstance(data, list):
        for item in data:
            found = _find_prediction_value(item, names)

            if found is not None:
                return found

    return None


def _normalize_prediction_json(data: Any) -> Dict[str, Any]:
    """
    Convert an engine JSON artifact into the common TOC prediction shape.
    """
    if not isinstance(data, (dict, list)):
        return {}

    aliases = {
        "top60": {"top60", "topsixty"},
        "top30": {"top30", "topthirty"},
        "top20": {"top20", "toptwenty"},
        "top10": {"top10", "topten"},
        "top5": {"top5", "topfive"},
        "top2": {"top2", "toptwo"},
    }

    prediction: Dict[str, Any] = {}

    for target_name, possible_names in aliases.items():
        value = _find_prediction_value(data, possible_names)

        numbers = _prediction_number_list(value)

        if numbers:
            prediction[target_name] = numbers

    banker = _find_prediction_value(
        data,
        {"banker", "bankernumber", "bestnumber"},
    )

    if banker is not None:
        try:
            prediction["banker"] = int(banker)
        except (TypeError, ValueError):
            banker_numbers = _prediction_number_list(banker)

            if banker_numbers:
                prediction["banker"] = banker_numbers[0]

    confidence = _find_prediction_value(
        data,
        {"confidence", "confidencescore", "score"},
    )

    if confidence is not None:
        try:
            prediction["confidence"] = float(confidence)
        except (TypeError, ValueError):
            pass

    return prediction


def _parse_prediction_stdout(stdout: str) -> Dict[str, Any]:
    """
    Parse prediction values printed by an engine.

    Desmond currently prints lines such as:
      Top 60: ...
      Top 30: ...
      Top 20: ...
      Top 10: ...
      Top 5: ...
      Top 2: ...
      Banker: ...
      Confidence: ...
    """
    if not stdout:
        return {}

    prediction: Dict[str, Any] = {}

    levels = {
        "top60": 60,
        "top30": 30,
        "top20": 20,
        "top10": 10,
        "top5": 5,
        "top2": 2,
    }

    for field_name, level in levels.items():
        match = re.search(
            rf"Top\s*{level}\s*:\s*([^\r\n]+)",
            stdout,
            flags=re.IGNORECASE,
        )

        if match:
            values = _prediction_number_list(match.group(1))

            if values:
                prediction[field_name] = values

    banker_match = re.search(
        r"Banker\s*:\s*(\d{1,2})",
        stdout,
        flags=re.IGNORECASE,
    )

    if banker_match:
        prediction["banker"] = int(banker_match.group(1))

    confidence_match = re.search(
        r"Confidence\s*:\s*([0-9]*\.?[0-9]+)",
        stdout,
        flags=re.IGNORECASE,
    )

    if confidence_match:
        prediction["confidence"] = float(
            confidence_match.group(1)
        )

    return prediction


def _json_paths_from_stdout(stdout: str) -> list[Path]:
    """
    Find Windows JSON artifact paths written by an engine.
    """
    if not stdout:
        return []

    matches = re.findall(
        r"[A-Za-z]:\\[^\r\n\"]+?\.json",
        stdout,
    )

    paths: list[Path] = []

    for match in matches:
        path = Path(match.strip())

        if path.exists() and path.is_file():
            paths.append(path)

    return paths


def _load_prediction_from_engine_json(
    stdout: str,
) -> tuple[Dict[str, Any], Optional[str]]:
    """
    Read JSON artifacts reported in stdout and extract prediction fields.

    This is particularly important for Kadija because Kadija writes
    structured JSON artifacts even when its console output does not print
    all prediction levels.
    """
    paths = _json_paths_from_stdout(stdout)

    # Work backwards because the latest path printed is normally
    # the final artifact created by the engine.
    for path in reversed(paths):
        try:
            with path.open(
                "r",
                encoding="utf-8",
            ) as handle:
                data = json.load(handle)

            prediction = _normalize_prediction_json(data)

            if prediction:
                return prediction, str(path)

        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):
            continue

    return {}, None


def _enrich_engine_result(
    result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Add structured prediction values to an existing engine result
    without changing the engine execution itself.
    """
    enriched = dict(result)

    stdout = str(result.get("stdout") or "")

    # First parse anything explicitly printed by the engine.
    prediction = _parse_prediction_stdout(stdout)

    artifact_path: Optional[str] = None

    # Then inspect JSON artifacts. This gives Kadija structured output
    # without modifying Kadija itself.
    artifact_prediction, artifact_path = (
        _load_prediction_from_engine_json(stdout)
    )

    # stdout values win when both sources contain the same field.
    prediction = {
        **artifact_prediction,
        **prediction,
    }

    enriched["prediction"] = prediction

    if artifact_path:
        enriched["prediction_artifact"] = artifact_path

    # Also expose the standard fields directly on the engine result.
    # This keeps the API easy for the current React page to consume.
    for field_name in (
        "top60",
        "top30",
        "top20",
        "top10",
        "top5",
        "top2",
        "banker",
        "confidence",
    ):
        if field_name in prediction:
            enriched[field_name] = prediction[field_name]

    return enriched


def _validate_engine_prediction_result(
    result: Dict[str, Any],
) -> Dict[str, Any]:
    """Require the fields the Prediction Engines UI needs before success."""
    if result.get("status") != "success":
        return result

    if not _engine_prediction_is_usable(result):
        prediction = result.get("prediction")
        if not isinstance(prediction, dict):
            prediction = {}

        missing: list[str] = []
        for field_name in ("top5", "top2"):
            if not _prediction_number_list(prediction.get(field_name)):
                missing.append(field_name)

        try:
            int(prediction.get("banker"))
        except (TypeError, ValueError):
            missing.append("banker")

        confidence = prediction.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            missing.append("confidence")

        invalid = dict(result)
        invalid["status"] = "error"
        invalid["message"] = (
            "Engine exited successfully but did not return usable "
            f"prediction fields: {', '.join(missing)}."
        )
        return invalid

    return result

@app.post("/api/prediction-engines/run")
def prediction_engines_run():
    payload = request.get_json(silent=True) or {}

    game_name = payload.get("game")

    try:
        canonical_game = _canonical_game_name(game_name)
        game_id = _resolve_kadija_game_id(
            canonical_game
        )

    except Exception as exc:
        return jsonify(
            {
                "status": "error",
                "message": f"Could not validate selected game: {exc}",
                "game": game_name if isinstance(game_name, str) else "",
            }
        ), 400

    results = [
            _run_prediction_engine(
                engine_name="Kadija",
                script_path=KADIJA_ENGINE,
                game_name=canonical_game,
                game_id=game_id,
            ),
            _run_prediction_engine(
                engine_name="Desmond",
                script_path=DESMOND_ENGINE,
                game_name=canonical_game,
                game_id=game_id,
            ),
        ]

    results = [
        _validate_engine_prediction_result(
            _enrich_engine_result(result)
        )
        for result in results
    ]

    failed = [
            result
            for result in results
            if result.get("status") != "success"
        ]

    if failed:
            overall_status = (
                "error"
                if len(failed) == len(results)
                else "partial_failure"
            )
            message = (
                "Prediction engines failed."
                if overall_status == "error"
                else "One or more prediction engines failed."
            )
            return (
                jsonify(
                    {
                        "status": overall_status,
                        "message": message,
                        "game": canonical_game,
                        "game_id": game_id,
                        "results": results,
                    }
                ),
                500,
            )

    success_payload = {
            "status": "success",
            "message": "Prediction engines completed successfully.",
            "game": canonical_game,
            "game_id": game_id,
            "results": results,
        }
    try:
            _save_latest_prediction_run(success_payload)
    except (OSError, TypeError, ValueError) as exc:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": (
                            "Prediction engines completed, but the "
                            "latest result could not be saved."
                        ),
                        "game": canonical_game,
                        "game_id": game_id,
                        "results": results,
                        "detail": str(exc),
                    }
                ),
                500,
            )

    return jsonify(success_payload), 200

@app.post("/api/theresa/run")
def theresa_run():
    payload = request.get_json(silent=True) or {}

    target_game = payload.get(
        "game",
        DEFAULT_TARGET_GAME,
    )
    source_mode = payload.get(
        "source_mode",
        "auto",
    )
    lookback = payload.get(
        "lookback",
        0,
    )
    trigger_depth = payload.get(
        "trigger_depth",
        3,
    )
    min_consistency = payload.get(
        "min_consistency",
        2,
    )

    try:
        result = run_theresa(
            target_game=target_game,
            source_mode=source_mode,
            lookback=int(lookback),
            trigger_depth=int(trigger_depth),
            min_consistency=int(
                min_consistency
            ),
        )
        return jsonify(result)

    except Exception as exc:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": str(exc),
                }
            ),
            500,
        )


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5050,
        debug=False,
    )

