#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
THERESA MACHINE-AWARE HYBRID PREDICTOR v4.0
===========================================

Production-ready single-file Theresa engine for the Consensus Intelligence Platform.

Core capabilities:
- Old-machine trigger -> follower analysis
- New-machine transition / travel / structure analysis
- Automatic machine-family detection
- Adaptive confidence scoring
- Full Top60 output
- Local JSON archive
- DOCX summary report
- CIP JSON export copy
- engine_manifest.json
- Backtest mode
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import re
import shutil
import hashlib
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    from engine_data_service import get_data_service, DataServiceError
except ImportError as exc:
    raise RuntimeError(
        "Theresa TOC requires backend/engine_data_service.py on PYTHONPATH"
    ) from exc

try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    Document = None


ENGINE_KEY = "theresa"
ENGINE_NAME = "Theresa Machine-Aware Hybrid Predictor"
ENGINE_VERSION = "4.0.0-toc"
SCRIPT_NAME = "theresa_engine_toc.py"

FIELD_MIN = 1
FIELD_MAX = 90
DEFAULT_TARGET_GAME = "vag friday"

NEW_MACHINE_GAMES_4 = [
    "monday special",
    "wednesday midweek",
    "friday bonanza",
    "saturday national",
]

OLD_MACHINE_GAMES_15 = [
    "sunday aseda",
    "vag monday",
    "noon monday",
    "vag tuesday",
    "noon tuesday",
    "lucky tuesday",
    "vag wednesday",
    "noon wednesday",
    "vag thursday",
    "noon thursday",
    "fortune thursday",
    "vag friday",
    "noon friday",
    "vag saturday",
    "noon saturday",
]

ALL_GAMES = NEW_MACHINE_GAMES_4 + OLD_MACHINE_GAMES_15

THERESA_CONFIG = {
    "old_machine": {
        "recency_decay": 0.015,
        "source_machine_weight": 1.15,
        "cross_machine_support_weight": 0.70,
        "follow_strength_weight": 0.78,
        "gap_weight": 0.10,
        "frequency_weight": 0.07,
        "structure_weight": 0.05,
        "recent_penalties": [0.58, 0.78, 0.88],
        "trigger_self_penalty": 0.68,
    },
    "new_machine": {
        "lookback_default": 80,
        "recency_decay": 0.018,
        "new_source_weight": 1.25,
        "old_support_weight": 0.75,
        "transition_weight": 0.62,
        "structure_weight": 0.16,
        "gap_weight": 0.12,
        "frequency_weight": 0.10,
        "recent_penalties": [0.58, 0.78, 0.88],
    },
    "confidence": {
        "score_strength": 0.40,
        "consistency": 0.25,
        "diversity": 0.20,
        "position": 0.15,
        "new_machine_adjustment": 0.97,
        "floor": 0.05,
        "ceiling": 0.99,
    },
}

HOME = Path.home()
DOCUMENTS = HOME / "Documents"
MASTER_DATA = DOCUMENTS / "MASTER_DATA"
ROOT = DOCUMENTS / "Banger_Tracker" / "Theresa_Predictor"
INPUT_STREAM = ROOT / "input_stream"
SUMMARIES = ROOT / "summaries"
REPORTS = ROOT / "reports"
LOGS = ROOT / "logs"
BACKTEST_DIR = ROOT / "backtest"
MODELS = ROOT / "models"
MANIFEST_FILE = ROOT / "engine_manifest.json"

CIP_EXPORT_DIR = (
    DOCUMENTS
    / "Consensus_Predictor"
    / "Fusion_Memory"
    / "input_streams"
    / "theresa"
)

for folder in [ROOT, INPUT_STREAM, SUMMARIES, REPORTS, LOGS, BACKTEST_DIR, MODELS, CIP_EXPORT_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - THERESA - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOGS / "theresa_predictor.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("TheresaPredictor")


def normalize_game_name(name: str) -> str:
    text = str(name).lower().strip().replace("_", " ").replace("-", " ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def safe_file_name(name: str) -> str:
    return normalize_game_name(name).replace(" ", "_")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def unique_keep_order(nums: List[int]) -> List[int]:
    output: List[int] = []
    for x in nums:
        try:
            n = int(x)
        except Exception:
            continue
        if FIELD_MIN <= n <= FIELD_MAX and n not in output:
            output.append(n)
    return output


def to_json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_json_safe(v) for v in obj]
    if isinstance(obj, tuple):
        return [to_json_safe(v) for v in obj]
    if isinstance(obj, set):
        return sorted(list(obj))
    if isinstance(obj, Counter):
        return dict(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def nums_text(nums: List[int]) -> str:
    return " - ".join(f"{int(n):02d}" for n in nums)


def machine_family(game: str) -> str:
    g = normalize_game_name(game)
    if g in NEW_MACHINE_GAMES_4:
        return "new_machine"
    if g in OLD_MACHINE_GAMES_15:
        return "old_machine"
    return "unknown"


def is_old_machine(game: str) -> bool:
    return machine_family(game) == "old_machine"


def is_new_machine(game: str) -> bool:
    return machine_family(game) == "new_machine"


def is_valid_canonical_draw(nums: List[int]) -> bool:
    """Validate canonical shape/range without imposing number uniqueness."""
    if len(nums) != 5:
        return False
    try:
        values = [int(n) for n in nums]
    except Exception:
        return False
    return all(FIELD_MIN <= n <= FIELD_MAX for n in values)


def build_trigger_memory(target_draws: List[List[int]], trigger_depth: int) -> List[int]:
    depth = max(1, int(trigger_depth))
    draws = target_draws[-depth:] if len(target_draws) >= depth else target_draws
    return sorted(set(n for draw in draws for n in draw))


def normalize_scores(scores: Dict[int, float]) -> Dict[int, float]:
    if not scores:
        return {}
    min_s = min(scores.values())
    max_s = max(scores.values())
    if max_s > min_s:
        return {n: (v - min_s) / (max_s - min_s) for n, v in scores.items()}
    return {n: 0.5 for n in scores}


def load_all_games() -> Dict[str, List[Dict[str, Any]]]:
    """Load all Theresa histories exclusively through TOC engine_data_service."""
    all_draws: Dict[str, List[Dict[str, Any]]] = {}
    try:
        service = get_data_service()
    except Exception as exc:
        raise RuntimeError(f"Unable to initialize TOC engine data service: {exc}") from exc

    for game in ALL_GAMES:
        game_norm = normalize_game_name(game)
        try:
            records = service.records(game_norm)
        except (DataServiceError, KeyError, ValueError, TypeError) as exc:
            logger.warning("Canonical data unavailable for %s: %s", game_norm, exc)
            continue

        rows: List[Dict[str, Any]] = []
        for record in records:
            nums = [int(n) for n in record.draw_numbers]
            if not is_valid_canonical_draw(nums):
                raise RuntimeError(
                    f"Invalid canonical draw returned by data service for {game_norm}: {nums}"
                )
            rows.append({"date": record.iso_date, "numbers": nums})

        if rows:
            all_draws[game_norm] = rows
            logger.info(
                "Loaded %d canonical draws for %s via engine_data_service (latest=%s)",
                len(rows), game_norm, rows[-1]["date"],
            )
        else:
            logger.warning("No canonical draws available for %s", game_norm)

    return all_draws


def canonical_dataset_checksum(all_draws: Dict[str, List[Dict[str, Any]]]) -> str:
    payload = {
        game: [{"date": r.get("date", ""), "numbers": r.get("numbers", [])} for r in rows]
        for game, rows in sorted(all_draws.items())
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def get_number_draws(game_rows: List[Dict[str, Any]]) -> List[List[int]]:
    return [row["numbers"] for row in game_rows]


def select_source_games(all_draws: Dict[str, List[Dict[str, Any]]], target_game: str, mode: str = "auto") -> List[str]:
    target = normalize_game_name(target_game)

    if mode == "auto":
        if is_old_machine(target):
            pool = OLD_MACHINE_GAMES_15
        elif is_new_machine(target):
            pool = NEW_MACHINE_GAMES_4 + OLD_MACHINE_GAMES_15
        else:
            return [g for g in all_draws if g != target]
    elif mode == "old15":
        pool = OLD_MACHINE_GAMES_15
    elif mode == "new4":
        pool = NEW_MACHINE_GAMES_4
    elif mode == "new4_plus_old_support":
        pool = NEW_MACHINE_GAMES_4 + OLD_MACHINE_GAMES_15
    elif mode == "all_except_target":
        return [g for g in all_draws if g != target]
    else:
        pool = OLD_MACHINE_GAMES_15

    return [normalize_game_name(g) for g in pool if normalize_game_name(g) in all_draws and normalize_game_name(g) != target]


def source_machine_weight(source_game: str, target_game: str) -> float:
    source = normalize_game_name(source_game)
    target = normalize_game_name(target_game)

    if is_new_machine(target):
        if is_new_machine(source):
            return float(THERESA_CONFIG["new_machine"]["new_source_weight"])
        if is_old_machine(source):
            return float(THERESA_CONFIG["new_machine"]["old_support_weight"])
        return 1.0

    if is_old_machine(target):
        if is_old_machine(source):
            return float(THERESA_CONFIG["old_machine"]["source_machine_weight"])
        if is_new_machine(source):
            return float(THERESA_CONFIG["old_machine"]["cross_machine_support_weight"])
        return 1.0

    return 1.0


def compute_target_gap_features(target_draws: List[List[int]]) -> Dict[int, Dict[str, float]]:
    features: Dict[int, Dict[str, float]] = {}

    for n in range(FIELD_MIN, FIELD_MAX + 1):
        seen = [i for i, draw in enumerate(target_draws) if n in draw]

        if not seen:
            features[n] = {
                "current_gap": float(len(target_draws)),
                "avg_gap": float(len(target_draws)),
                "gap_score": 0.5,
                "target_frequency": 0.0,
            }
            continue

        current_gap = len(target_draws) - 1 - seen[-1]
        gaps = [seen[i] - seen[i - 1] for i in range(1, len(seen))]
        avg_gap = float(np.mean(gaps)) if gaps else float(max(1, current_gap))
        target_frequency = len(seen) / max(1, len(target_draws))
        ratio = current_gap / avg_gap if avg_gap > 0 else 0

        if ratio < 0.35:
            gap_score = 0.15
        elif ratio < 0.75:
            gap_score = 0.45
        elif ratio < 1.35:
            gap_score = 1.0
        elif ratio < 2.25:
            gap_score = 0.85
        else:
            gap_score = 0.45

        features[n] = {
            "current_gap": float(current_gap),
            "avg_gap": float(avg_gap),
            "gap_score": float(gap_score),
            "target_frequency": float(target_frequency),
        }

    return features


def compute_recent_suppression(target_draws: List[List[int]], family: str) -> Dict[int, float]:
    if family == "new_machine":
        penalties = THERESA_CONFIG["new_machine"]["recent_penalties"]
    else:
        penalties = THERESA_CONFIG["old_machine"]["recent_penalties"]

    penalty = {n: 1.0 for n in range(FIELD_MIN, FIELD_MAX + 1)}

    for depth, factor in enumerate(penalties, start=1):
        if len(target_draws) >= depth:
            for n in target_draws[-depth]:
                penalty[n] *= float(factor)

    return penalty


def structure_profile(draw: List[int]) -> Dict[str, Any]:
    nums = unique_keep_order(draw)
    if not nums:
        return {"odd": 0, "even": 0, "low": 0, "high": 0, "sum": 0, "span": 0, "decades": {}}

    odd = sum(1 for n in nums if n % 2 == 1)
    even = len(nums) - odd
    low = sum(1 for n in nums if n <= 45)
    high = len(nums) - low
    decades = Counter((n - 1) // 10 for n in nums)

    return {
        "odd": odd,
        "even": even,
        "low": low,
        "high": high,
        "sum": sum(nums),
        "span": max(nums) - min(nums),
        "decades": dict(decades),
    }


def structure_score_number(n: int, target_draws: List[List[int]], lookback: int = 12) -> float:
    if not target_draws:
        return 0.5

    recent = target_draws[-lookback:]
    count = sum(1 for draw in recent if n in draw)
    freq = count / max(1, len(recent))

    decade = (n - 1) // 10
    decade_count = 0
    total_slots = 0

    for draw in recent:
        for x in draw:
            total_slots += 1
            if (x - 1) // 10 == decade:
                decade_count += 1

    decade_freq = decade_count / max(1, total_slots)
    score = (0.65 * min(freq * 4.0, 1.0)) + (0.35 * min(decade_freq * 8.0, 1.0))
    return float(max(0.05, min(score, 1.0)))


def analyze_trigger_followers(
    all_draws: Dict[str, List[Dict[str, Any]]],
    target_game: str,
    trigger_draw: List[int],
    source_games: List[str],
    lookback: int = 0,
) -> Tuple[Dict[int, Dict[str, Any]], List[Dict[str, Any]]]:
    target_game = normalize_game_name(target_game)
    trigger_set = set(trigger_draw)

    stats: Dict[int, Dict[str, Any]] = {}

    for n in range(FIELD_MIN, FIELD_MAX + 1):
        stats[n] = {
            "raw_count": 0.0,
            "weighted_count": 0.0,
            "source_games": set(),
            "trigger_numbers": set(),
            "positions": Counter(),
            "events": [],
            "draw_keys": set(),
            "trigger_position_counter": Counter(),
            "follower_position_counter": Counter(),
            "source_game_counter": Counter(),
            "trigger_counter": Counter(),
            "signal_pair_counter": Counter(),
        }

    event_rows: List[Dict[str, Any]] = []
    recency_decay = float(THERESA_CONFIG["old_machine"]["recency_decay"])

    for game in source_games:
        rows = all_draws.get(game, [])
        if len(rows) < 2:
            continue

        machine_weight = source_machine_weight(game, target_game)
        search_rows = rows[-lookback:] if lookback and lookback > 0 else rows
        offset = len(rows) - len(search_rows)

        for local_i, row in enumerate(search_rows):
            i = offset + local_i
            if i >= len(rows) - 1:
                continue

            current_draw = row["numbers"]
            next_draw = rows[i + 1]["numbers"]
            hits = trigger_set.intersection(current_draw)

            if not hits:
                continue

            current_date = row.get("date", "")
            next_date = rows[i + 1].get("date", "")
            draw_key = f"{game}|{current_date}|{next_date}|{i}"

            age_from_end = (len(rows) - 2) - i
            recency_weight = math.exp(-recency_decay * max(age_from_end, 0))
            multi_trigger_boost = 1.0 + 0.15 * (len(hits) - 1)

            for trigger in sorted(hits):
                trigger_pos = current_draw.index(trigger) + 1 if trigger in current_draw else 0

                for follower_pos, follower in enumerate(next_draw, start=1):
                    weight = recency_weight * multi_trigger_boost * machine_weight

                    if trigger_pos and follower_pos == trigger_pos:
                        weight *= 1.15
                    elif trigger_pos and abs(follower_pos - trigger_pos) == 1:
                        weight *= 1.07

                    s = stats[follower]
                    s["raw_count"] += 1.0
                    s["weighted_count"] += weight
                    s["source_games"].add(game)
                    s["trigger_numbers"].add(trigger)
                    s["positions"][follower_pos] += 1
                    s["draw_keys"].add(draw_key)
                    s["trigger_position_counter"][trigger_pos] += 1
                    s["follower_position_counter"][follower_pos] += 1
                    s["source_game_counter"][game] += 1
                    s["trigger_counter"][trigger] += 1
                    s["signal_pair_counter"][(game, trigger, trigger_pos, follower, follower_pos)] += 1

                    event = {
                        "source_game": game,
                        "source_machine_weight": round(machine_weight, 4),
                        "target_game": target_game,
                        "trigger_number": trigger,
                        "trigger_position": trigger_pos,
                        "trigger_date": current_date,
                        "trigger_draw": current_draw,
                        "follower_number": follower,
                        "follower_position": follower_pos,
                        "next_date": next_date,
                        "next_draw": next_draw,
                        "draw_key": draw_key,
                        "recency_weight": round(recency_weight, 5),
                        "event_weight": round(weight, 5),
                    }
                    s["events"].append(event)
                    event_rows.append(event)

    max_weighted = max((v["weighted_count"] for v in stats.values()), default=1.0) or 1.0
    max_raw = max((v["raw_count"] for v in stats.values()), default=1.0) or 1.0
    max_sources = max((len(v["source_games"]) for v in stats.values()), default=1) or 1
    max_triggers = max((len(v["trigger_numbers"]) for v in stats.values()), default=1) or 1
    max_consistency = max((len(v["draw_keys"]) for v in stats.values()), default=1) or 1

    for _, s in stats.items():
        s["source_count"] = len(s["source_games"])
        s["trigger_coverage"] = len(s["trigger_numbers"])
        s["consistency_count"] = len(s["draw_keys"])
        s["weighted_norm"] = s["weighted_count"] / max_weighted
        s["raw_norm"] = s["raw_count"] / max_raw
        s["source_norm"] = s["source_count"] / max_sources
        s["trigger_norm"] = s["trigger_coverage"] / max_triggers
        s["consistency_rate"] = s["consistency_count"] / max_consistency

        if s["positions"]:
            s["best_position"] = s["positions"].most_common(1)[0][0]
            s["position_consistency"] = s["positions"].most_common(1)[0][1] / max(1, sum(s["positions"].values()))
        else:
            s["best_position"] = None
            s["position_consistency"] = 0.0

        s["best_source_game"] = s["source_game_counter"].most_common(1)[0][0] if s["source_game_counter"] else None
        s["best_trigger_number"] = s["trigger_counter"].most_common(1)[0][0] if s["trigger_counter"] else None
        s["best_trigger_position"] = s["trigger_position_counter"].most_common(1)[0][0] if s["trigger_position_counter"] else None
        s["best_follower_position"] = s["follower_position_counter"].most_common(1)[0][0] if s["follower_position_counter"] else None
        s["source_games"] = sorted(s["source_games"])
        s["trigger_numbers"] = sorted(s["trigger_numbers"])

    return stats, event_rows


def extract_strongest_signals(follower_stats: Dict[int, Dict[str, Any]], limit: int = 40) -> List[Dict[str, Any]]:
    signals: List[Dict[str, Any]] = []

    for _, s in follower_stats.items():
        for signal_key, count in s.get("signal_pair_counter", Counter()).items():
            source_game, trigger_number, trigger_position, follower_number, follower_position = signal_key
            signals.append({
                "source_game": source_game,
                "trigger_number": trigger_number,
                "trigger_position": trigger_position,
                "follower_number": follower_number,
                "follower_position": follower_position,
                "signal_count": int(count),
                "follower_consistency_count": int(s.get("consistency_count", 0)),
                "follower_consistency_rate": round(float(s.get("consistency_rate", 0.0)), 4),
                "source_count": int(s.get("source_count", 0)),
                "trigger_coverage": int(s.get("trigger_coverage", 0)),
                "weighted_count": round(float(s.get("weighted_count", 0.0)), 5),
                "raw_count": int(s.get("raw_count", 0)),
            })

    signals.sort(
        key=lambda x: (
            x["follower_consistency_count"],
            x["follower_consistency_rate"],
            x["signal_count"],
            x["source_count"],
            x["trigger_coverage"],
            x["weighted_count"],
        ),
        reverse=True,
    )
    return signals[:limit]


def score_old_machine_followers(
    follower_stats: Dict[int, Dict[str, Any]],
    target_draws: List[List[int]],
    trigger_draw: List[int],
    min_consistency: int = 2,
) -> Dict[int, float]:
    cfg = THERESA_CONFIG["old_machine"]
    gap_features = compute_target_gap_features(target_draws)
    recent_penalty = compute_recent_suppression(target_draws, "old_machine")
    min_consistency = max(1, int(min_consistency))

    scores: Dict[int, float] = {}

    for n in range(FIELD_MIN, FIELD_MAX + 1):
        s = follower_stats[n]

        follow_strength = (
            0.34 * s.get("consistency_rate", 0.0)
            + 0.20 * s.get("source_norm", 0.0)
            + 0.17 * s.get("trigger_norm", 0.0)
            + 0.14 * s.get("weighted_norm", 0.0)
            + 0.10 * s.get("raw_norm", 0.0)
            + 0.05 * s.get("position_consistency", 0.0)
        )

        gap_score = gap_features[n]["gap_score"]
        target_frequency_score = min(1.0, gap_features[n]["target_frequency"] * 12.0)
        structural = structure_score_number(n, target_draws)

        score = (
            float(cfg["follow_strength_weight"]) * follow_strength
            + float(cfg["gap_weight"]) * gap_score
            + float(cfg["frequency_weight"]) * target_frequency_score
            + float(cfg["structure_weight"]) * structural
        )

        score *= recent_penalty[n]

        if n in trigger_draw:
            score *= float(cfg["trigger_self_penalty"])

        if s.get("consistency_count", 0) < min_consistency:
            score *= 0.05

        if s.get("source_count", 0) <= 1 and s.get("trigger_coverage", 0) <= 1:
            score *= 0.60

        if s.get("weighted_count", 0.0) <= 0 and gap_features[n]["target_frequency"] < 0.04:
            score *= 0.25

        scores[n] = float(score)

    return normalize_scores(scores)


def analyze_new_machine_transitions(
    all_draws: Dict[str, List[Dict[str, Any]]],
    target_game: str,
    lookback: int = 80,
) -> Dict[int, Dict[str, Any]]:
    target_game = normalize_game_name(target_game)
    stats: Dict[int, Dict[str, Any]] = {}

    for n in range(FIELD_MIN, FIELD_MAX + 1):
        stats[n] = {
            "transition_count": 0.0,
            "weighted_transition": 0.0,
            "source_games": set(),
            "source_numbers": Counter(),
            "position_counter": Counter(),
            "travel_events": [],
        }

    target_rows = all_draws.get(target_game, [])
    if not target_rows:
        return stats

    source_games = [g for g in NEW_MACHINE_GAMES_4 if g in all_draws and g != target_game]
    recency_decay = float(THERESA_CONFIG["new_machine"]["recency_decay"])

    for source_game in source_games:
        source_rows = all_draws.get(source_game, [])
        if len(source_rows) < 2:
            continue

        usable = min(len(source_rows), len(target_rows))
        start = max(0, usable - lookback)

        for i in range(start, usable):
            source_draw = source_rows[i]["numbers"]
            target_draw = target_rows[i]["numbers"]
            age = usable - 1 - i
            recency = math.exp(-recency_decay * max(age, 0))
            machine_boost = source_machine_weight(source_game, target_game)

            sp = structure_profile(source_draw)
            tp = structure_profile(target_draw)

            structure_bonus = 1.0
            if abs(sp["odd"] - tp["odd"]) <= 1:
                structure_bonus *= 1.06
            if abs(sp["low"] - tp["low"]) <= 1:
                structure_bonus *= 1.06

            for source_pos, source_n in enumerate(source_draw, start=1):
                for follower_pos, follower in enumerate(target_draw, start=1):
                    weight = recency * machine_boost * structure_bonus

                    if source_pos == follower_pos:
                        weight *= 1.12
                    elif abs(source_pos - follower_pos) == 1:
                        weight *= 1.06

                    s = stats[follower]
                    s["transition_count"] += 1.0
                    s["weighted_transition"] += weight
                    s["source_games"].add(source_game)
                    s["source_numbers"][source_n] += 1
                    s["position_counter"][follower_pos] += 1
                    s["travel_events"].append({
                        "source_game": source_game,
                        "source_number": source_n,
                        "source_position": source_pos,
                        "target_game": target_game,
                        "follower_number": follower,
                        "follower_position": follower_pos,
                        "weight": round(weight, 5),
                    })

    max_weight = max((v["weighted_transition"] for v in stats.values()), default=1.0) or 1.0
    max_count = max((v["transition_count"] for v in stats.values()), default=1.0) or 1.0
    max_sources = max((len(v["source_games"]) for v in stats.values()), default=1) or 1

    for _, s in stats.items():
        s["source_count"] = len(s["source_games"])
        s["weighted_norm"] = s["weighted_transition"] / max_weight
        s["count_norm"] = s["transition_count"] / max_count
        s["source_norm"] = s["source_count"] / max_sources
        s["source_games"] = sorted(s["source_games"])

        if s["position_counter"]:
            s["best_position"] = s["position_counter"].most_common(1)[0][0]
            s["position_consistency"] = s["position_counter"].most_common(1)[0][1] / max(1, sum(s["position_counter"].values()))
        else:
            s["best_position"] = None
            s["position_consistency"] = 0.0

        s["best_source_number"] = s["source_numbers"].most_common(1)[0][0] if s["source_numbers"] else None

    return stats


def score_new_machine_candidates(
    transition_stats: Dict[int, Dict[str, Any]],
    target_draws: List[List[int]],
) -> Dict[int, float]:
    cfg = THERESA_CONFIG["new_machine"]
    gap_features = compute_target_gap_features(target_draws)
    recent_penalty = compute_recent_suppression(target_draws, "new_machine")
    scores: Dict[int, float] = {}

    for n in range(FIELD_MIN, FIELD_MAX + 1):
        s = transition_stats[n]
        transition_strength = (
            0.38 * s.get("weighted_norm", 0.0)
            + 0.22 * s.get("source_norm", 0.0)
            + 0.16 * s.get("count_norm", 0.0)
            + 0.12 * s.get("position_consistency", 0.0)
        )

        structural = structure_score_number(n, target_draws)
        gap_score = gap_features[n]["gap_score"]
        frequency_score = min(1.0, gap_features[n]["target_frequency"] * 12.0)

        score = (
            float(cfg["transition_weight"]) * transition_strength
            + float(cfg["structure_weight"]) * structural
            + float(cfg["gap_weight"]) * gap_score
            + float(cfg["frequency_weight"]) * frequency_score
        )

        score *= recent_penalty[n]

        if s.get("source_count", 0) <= 0 and gap_features[n]["target_frequency"] < 0.04:
            score *= 0.40

        scores[n] = float(score)

    return normalize_scores(scores)


def compute_prediction_confidence(
    scores: Dict[int, float],
    top_numbers: List[int],
    family: str,
    follower_stats: Optional[Dict[int, Dict[str, Any]]] = None,
    transition_stats: Optional[Dict[int, Dict[str, Any]]] = None,
) -> float:
    if not top_numbers:
        return 0.0

    cfg = THERESA_CONFIG["confidence"]
    score_strength = float(np.mean([scores.get(n, 0.0) for n in top_numbers]))
    consistency_values = []
    diversity_values = []
    position_values = []

    for n in top_numbers:
        if follower_stats and n in follower_stats:
            s = follower_stats[n]
            consistency_values.append(float(s.get("consistency_rate", 0.0)))
            diversity_values.append(float(s.get("source_norm", 0.0)))
            position_values.append(float(s.get("position_consistency", 0.0)))
        elif transition_stats and n in transition_stats:
            s = transition_stats[n]
            consistency_values.append(float(s.get("weighted_norm", 0.0)))
            diversity_values.append(float(s.get("source_norm", 0.0)))
            position_values.append(float(s.get("position_consistency", 0.0)))

    consistency = float(np.mean(consistency_values)) if consistency_values else 0.0
    diversity = float(np.mean(diversity_values)) if diversity_values else 0.0
    position = float(np.mean(position_values)) if position_values else 0.0

    confidence = (
        float(cfg["score_strength"]) * score_strength
        + float(cfg["consistency"]) * consistency
        + float(cfg["diversity"]) * diversity
        + float(cfg["position"]) * position
    )

    if family == "new_machine":
        confidence *= float(cfg["new_machine_adjustment"])

    confidence = max(float(cfg["floor"]), min(confidence, float(cfg["ceiling"])))
    return round(confidence, 4)


def build_prediction_package(
    scores: Dict[int, float],
    target_game: str,
    target_draws: List[List[int]],
    trigger_draw: List[int],
    source_games: List[str],
    trigger_depth: int,
    min_consistency: int,
    strategy: str,
    follower_stats: Optional[Dict[int, Dict[str, Any]]] = None,
    transition_stats: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top2 = [n for n, _ in ranked[:2]]
    top5 = [n for n, _ in ranked[:5]]
    top10 = [n for n, _ in ranked[:10]]
    top20 = [n for n, _ in ranked[:20]]
    top30 = [n for n, _ in ranked[:30]]
    top60 = [n for n, _ in ranked[:60]]
    banker = top10[0] if top10 else None

    target_game_norm = normalize_game_name(target_game)
    family = machine_family(target_game_norm)

    confidence = compute_prediction_confidence(
        scores=scores,
        top_numbers=top10,
        family=family,
        follower_stats=follower_stats,
        transition_stats=transition_stats,
    )

    prediction_strength = round(float(np.mean([scores.get(n, 0.0) for n in top10])) if top10 else 0.0, 4)
    candidate_details: List[Dict[str, Any]] = []

    for n, sc in ranked[:30]:
        detail: Dict[str, Any] = {
            "number": n,
            "score": round(float(sc), 5),
            "strategy": strategy,
        }

        if follower_stats and n in follower_stats:
            s = follower_stats[n]
            detail.update({
                "raw_count": int(s.get("raw_count", 0)),
                "weighted_count": round(float(s.get("weighted_count", 0.0)), 5),
                "consistency_count": int(s.get("consistency_count", 0)),
                "consistency_rate": round(float(s.get("consistency_rate", 0.0)), 4),
                "source_count": int(s.get("source_count", 0)),
                "trigger_coverage": int(s.get("trigger_coverage", 0)),
                "source_games": s.get("source_games", []),
                "trigger_numbers": s.get("trigger_numbers", []),
                "best_source_game": s.get("best_source_game"),
                "best_trigger_number": s.get("best_trigger_number"),
                "best_trigger_position": s.get("best_trigger_position"),
                "best_follower_position": s.get("best_follower_position"),
                "best_position": s.get("best_position"),
                "position_consistency": round(float(s.get("position_consistency", 0.0)), 4),
            })

        if transition_stats and n in transition_stats:
            s = transition_stats[n]
            detail.update({
                "transition_count": int(s.get("transition_count", 0)),
                "weighted_transition": round(float(s.get("weighted_transition", 0.0)), 5),
                "source_count": int(s.get("source_count", 0)),
                "source_games": s.get("source_games", []),
                "best_source_number": s.get("best_source_number"),
                "best_position": s.get("best_position"),
                "position_consistency": round(float(s.get("position_consistency", 0.0)), 4),
            })

        candidate_details.append(detail)

    pred: Dict[str, Any] = {
        "engine": ENGINE_KEY,
        "engine_name": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "script_name": SCRIPT_NAME,
        "game": target_game_norm,
        "target_game": target_game_norm,
        "machine_family": family,
        "strategy": strategy,
        "method": "machine_aware_hybrid_old_trigger_follow_new_transition_structure",
        "generated": now_iso(),
        "prediction_date": now_iso(),
        "trigger_depth": int(trigger_depth),
        "min_consistency": int(min_consistency),
        "trigger_memory_numbers": trigger_draw,
        "source_games": source_games,
        "banker": banker,
        "top2": top2,
        "top5": top5,
        "top10": top10,
        "top20": top20,
        "top30": top30,
        "top60": top60,
        "confidence": confidence,
        "prediction_strength": prediction_strength,
        "engine_confidence_model": "Theresa Confidence Engine v4.0",
        "candidate_details_top30": candidate_details,
        "target_recent_draws": target_draws[-5:],
    }

    if follower_stats:
        pred["strongest_trigger_follower_signals"] = extract_strongest_signals(follower_stats, limit=40)
    else:
        pred["strongest_trigger_follower_signals"] = []

    if transition_stats:
        pred["new_machine_transition_summary"] = [
            {
                "number": n,
                "weighted_transition": round(float(s.get("weighted_transition", 0.0)), 5),
                "source_count": int(s.get("source_count", 0)),
                "source_games": s.get("source_games", []),
                "best_source_number": s.get("best_source_number"),
                "best_position": s.get("best_position"),
            }
            for n, s in sorted(
                transition_stats.items(),
                key=lambda x: x[1].get("weighted_transition", 0.0),
                reverse=True,
            )[:40]
        ]
    else:
        pred["new_machine_transition_summary"] = []

    return pred


def theresa_predict(
    all_draws: Dict[str, List[Dict[str, Any]]],
    target_game: str,
    source_mode: str = "auto",
    lookback: int = 0,
    trigger_depth: int = 3,
    min_consistency: int = 2,
) -> Dict[str, Any]:
    target_game = normalize_game_name(target_game)
    if target_game not in all_draws:
        raise RuntimeError(f"Target game not found: {target_game}")

    target_rows = all_draws[target_game]
    target_draws = get_number_draws(target_rows)
    if not target_draws:
        raise RuntimeError(f"No target draws found for {target_game}")

    trigger_draw = build_trigger_memory(target_draws, trigger_depth)
    source_games = select_source_games(all_draws, target_game, mode=source_mode)
    family = machine_family(target_game)

    if family == "new_machine":
        lookback_eff = lookback if lookback > 0 else int(THERESA_CONFIG["new_machine"]["lookback_default"])
        strategy = "new_machine_transition_structure"
        transition_stats = analyze_new_machine_transitions(all_draws, target_game, lookback_eff)
        scores = score_new_machine_candidates(transition_stats, target_draws)
        pred = build_prediction_package(
            scores=scores,
            target_game=target_game,
            target_draws=target_draws,
            trigger_draw=trigger_draw,
            source_games=source_games,
            trigger_depth=trigger_depth,
            min_consistency=min_consistency,
            strategy=strategy,
            follower_stats=None,
            transition_stats=transition_stats,
        )
        pred["total_follow_events_found"] = 0
        pred["new_machine_logic"] = {
            "transition_model": True,
            "structure_model": True,
            "gap_model": True,
            "recent_suppression": True,
            "source_weighting": "new_machine_sources_boosted_old_machine_secondary_support",
            "lookback_used": lookback_eff,
        }
        return pred

    strategy = "old_machine_trigger_follower"
    follower_stats, event_rows = analyze_trigger_followers(
        all_draws=all_draws,
        target_game=target_game,
        trigger_draw=trigger_draw,
        source_games=source_games,
        lookback=lookback,
    )
    scores = score_old_machine_followers(follower_stats, target_draws, trigger_draw, min_consistency)
    pred = build_prediction_package(
        scores=scores,
        target_game=target_game,
        target_draws=target_draws,
        trigger_draw=trigger_draw,
        source_games=source_games,
        trigger_depth=trigger_depth,
        min_consistency=min_consistency,
        strategy=strategy,
        follower_stats=follower_stats,
        transition_stats=None,
    )
    pred["total_follow_events_found"] = len(event_rows)
    pred["old_machine_logic"] = {
        "trigger_follower_model": True,
        "position_model": True,
        "source_weighting": "old_machine_sources_boosted",
        "gap_model": True,
        "recent_suppression": True,
    }
    return pred


def theresa_backtest(
    all_draws: Dict[str, List[Dict[str, Any]]],
    target_game: str,
    min_train: int = 40,
    source_mode: str = "auto",
    lookback: int = 0,
    trigger_depth: int = 3,
    min_consistency: int = 2,
) -> Dict[str, Any]:
    target_game = normalize_game_name(target_game)
    if target_game not in all_draws:
        raise RuntimeError(f"Target game not found: {target_game}")

    target_rows = all_draws[target_game]
    target_draws = get_number_draws(target_rows)
    needed_train = max(min_train, trigger_depth + 2)

    if len(target_draws) <= needed_train:
        logger.warning("Not enough draws for backtest.")
        return {}

    details: List[Dict[str, Any]] = []
    banker_hits: List[bool] = []
    top2_hits: List[bool] = []
    top5_hits: List[bool] = []
    top10_hits: List[bool] = []
    top20_hits: List[bool] = []
    top30_hits: List[bool] = []
    top60_hits: List[bool] = []

    for i in range(needed_train, len(target_draws)):
        temp_all: Dict[str, List[Dict[str, Any]]] = {}
        for game, rows in all_draws.items():
            temp_all[game] = rows[:min(len(rows), i)]

        if target_game not in temp_all or len(temp_all[target_game]) < needed_train:
            continue

        pred = theresa_predict(temp_all, target_game, source_mode, lookback, trigger_depth, min_consistency)
        actual = set(target_draws[i])

        banker_hit = pred["banker"] in actual if pred["banker"] else False
        top2_hit = bool(set(pred["top2"]) & actual)
        top5_hit = bool(set(pred["top5"]) & actual)
        top10_hit = bool(set(pred["top10"]) & actual)
        top20_hit = bool(set(pred["top20"]) & actual)
        top30_hit = bool(set(pred["top30"]) & actual)
        top60_hit = bool(set(pred["top60"]) & actual)

        banker_hits.append(banker_hit)
        top2_hits.append(top2_hit)
        top5_hits.append(top5_hit)
        top10_hits.append(top10_hit)
        top20_hits.append(top20_hit)
        top30_hits.append(top30_hit)
        top60_hits.append(top60_hit)

        details.append({
            "step": i,
            "actual": sorted(list(actual)),
            "banker": pred["banker"],
            "top2": pred["top2"],
            "top5": pred["top5"],
            "top10": pred["top10"],
            "top20": pred["top20"],
            "top30": pred["top30"],
            "top60": pred["top60"],
            "banker_hit": bool(banker_hit),
            "top2_hit": bool(top2_hit),
            "top5_hit": bool(top5_hit),
            "top10_hit": bool(top10_hit),
            "top20_hit": bool(top20_hit),
            "top30_hit": bool(top30_hit),
            "top60_hit": bool(top60_hit),
            "strategy": pred.get("strategy"),
            "machine_family": pred.get("machine_family"),
            "confidence": pred.get("confidence"),
        })

        if len(details) % 20 == 0:
            logger.info(
                "Backtest %s step %d/%d | top5=%.3f | top10=%.3f | top20=%.3f",
                target_game,
                i,
                len(target_draws),
                float(np.mean(top5_hits)),
                float(np.mean(top10_hits)),
                float(np.mean(top20_hits)),
            )

    total = len(details)
    return {
        "summary": {
            "engine": ENGINE_KEY,
            "engine_name": ENGINE_NAME,
            "engine_version": ENGINE_VERSION,
            "script_name": SCRIPT_NAME,
            "game": target_game,
            "machine_family": machine_family(target_game),
            "test_draws": total,
            "min_train": min_train,
            "trigger_depth": int(trigger_depth),
            "min_consistency": int(min_consistency),
            "lookback": int(lookback),
            "source_mode": source_mode,
            "banker_rate": float(np.mean(banker_hits)) if total else 0.0,
            "top2_rate": float(np.mean(top2_hits)) if total else 0.0,
            "top5_rate": float(np.mean(top5_hits)) if total else 0.0,
            "top10_rate": float(np.mean(top10_hits)) if total else 0.0,
            "top20_rate": float(np.mean(top20_hits)) if total else 0.0,
            "top30_rate": float(np.mean(top30_hits)) if total else 0.0,
            "top60_rate": float(np.mean(top60_hits)) if total else 0.0,
            "generated": now_iso(),
        },
        "details": details,
    }


def save_prediction_docx(pred: Dict[str, Any], path: Path) -> None:
    if not DOCX_AVAILABLE:
        return

    doc = Document()
    doc.add_heading("THERESA MACHINE-AWARE HYBRID PREDICTOR v4.0", 0)
    doc.add_paragraph(f"Engine: {pred.get('engine_name')}")
    doc.add_paragraph(f"Version: {pred.get('engine_version')}")
    doc.add_paragraph(f"Game: {pred.get('game')}")
    doc.add_paragraph(f"Machine Family: {pred.get('machine_family')}")
    doc.add_paragraph(f"Strategy: {pred.get('strategy')}")
    doc.add_paragraph(f"Generated: {pred.get('generated')}")
    doc.add_paragraph(f"Confidence: {pred.get('confidence')}")
    doc.add_paragraph(f"Prediction Strength: {pred.get('prediction_strength')}")

    doc.add_heading("Prediction Packages", level=1)
    doc.add_paragraph(f"Banker: {pred['banker']:02d}" if pred.get("banker") else "Banker: None")
    doc.add_paragraph(f"Top2: {nums_text(pred.get('top2', []))}")
    doc.add_paragraph(f"Top5: {nums_text(pred.get('top5', []))}")
    doc.add_paragraph(f"Top10: {nums_text(pred.get('top10', []))}")
    doc.add_paragraph(f"Top20: {nums_text(pred.get('top20', []))}")
    doc.add_paragraph(f"Top30: {nums_text(pred.get('top30', []))}")
    doc.add_paragraph(f"Top60: {nums_text(pred.get('top60', []))}")

    doc.add_heading("Trigger / Source Information", level=1)
    doc.add_paragraph(f"Trigger Depth: {pred.get('trigger_depth')}")
    doc.add_paragraph(f"Minimum Consistency: {pred.get('min_consistency')}")
    doc.add_paragraph(f"Trigger Memory: {nums_text(pred.get('trigger_memory_numbers', []))}")
    doc.add_paragraph(f"Source Games: {', '.join(pred.get('source_games', []))}")
    doc.add_paragraph(f"Total Follow Events Found: {pred.get('total_follow_events_found', 0)}")

    doc.add_heading("Candidate Details - Top 30", level=1)
    table = doc.add_table(rows=1, cols=8)
    headers = ["No.", "Score", "Strategy", "Sources", "Best Source", "Best Trigger", "Best Pos", "Pos Cons."]
    for i, h in enumerate(headers):
        table.rows[0].cells[i].text = h

    for row in pred.get("candidate_details_top30", []):
        cells = table.add_row().cells
        cells[0].text = f"{row.get('number', 0):02d}"
        cells[1].text = str(row.get("score", ""))
        cells[2].text = str(row.get("strategy", ""))
        cells[3].text = str(row.get("source_count", ""))
        cells[4].text = str(row.get("best_source_game", row.get("best_source_number", "")))
        cells[5].text = str(row.get("best_trigger_number", ""))
        cells[6].text = str(row.get("best_position", ""))
        cells[7].text = str(row.get("position_consistency", ""))

    if pred.get("strongest_trigger_follower_signals"):
        doc.add_heading("Strongest Trigger -> Follower Signals", level=1)
        sig_table = doc.add_table(rows=1, cols=7)
        sig_headers = ["Source Game", "Trigger", "Trig Pos", "Follower", "Follow Pos", "Signal", "Consistency"]
        for i, h in enumerate(sig_headers):
            sig_table.rows[0].cells[i].text = h
        for sig in pred.get("strongest_trigger_follower_signals", [])[:40]:
            cells = sig_table.add_row().cells
            cells[0].text = str(sig.get("source_game"))
            cells[1].text = f"{sig.get('trigger_number', 0):02d}"
            cells[2].text = str(sig.get("trigger_position"))
            cells[3].text = f"{sig.get('follower_number', 0):02d}"
            cells[4].text = str(sig.get("follower_position"))
            cells[5].text = str(sig.get("signal_count"))
            cells[6].text = str(sig.get("follower_consistency_count"))

    if pred.get("new_machine_transition_summary"):
        doc.add_heading("New-Machine Transition Summary", level=1)
        tr_table = doc.add_table(rows=1, cols=6)
        tr_headers = ["Number", "Weighted", "Sources", "Source Games", "Best Source No.", "Best Pos"]
        for i, h in enumerate(tr_headers):
            tr_table.rows[0].cells[i].text = h
        for item in pred.get("new_machine_transition_summary", [])[:40]:
            cells = tr_table.add_row().cells
            cells[0].text = f"{item.get('number', 0):02d}"
            cells[1].text = str(item.get("weighted_transition"))
            cells[2].text = str(item.get("source_count"))
            cells[3].text = ", ".join(item.get("source_games", []))
            cells[4].text = str(item.get("best_source_number"))
            cells[5].text = str(item.get("best_position"))

    doc.add_heading("CIP Export", level=1)
    doc.add_paragraph("A JSON copy of this prediction is exported to the CIP input_streams/theresa folder.")
    doc.save(str(path))


def write_manifest(pred: Dict[str, Any], json_path: Path, docx_path: Optional[Path], cip_path: Path) -> None:
    manifest = {
        "engine": ENGINE_KEY,
        "engine_name": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "script_name": SCRIPT_NAME,
        "status": "SUCCESS",
        "last_prediction": now_iso(),
        "last_game": pred.get("game"),
        "machine_family": pred.get("machine_family"),
        "strategy": pred.get("strategy"),
        "latest_json": str(json_path),
        "latest_summary": str(docx_path) if docx_path else None,
        "latest_cip_export": str(cip_path),
    }
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def save_prediction(pred: Dict[str, Any]) -> Tuple[Path, Optional[Path], Path]:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    game_file = safe_file_name(pred["game"])
    base = f"Theresa_{game_file}_{ts}"
    json_path = INPUT_STREAM / f"{base}.json"
    json_path.write_text(json.dumps(to_json_safe(pred), indent=2), encoding="utf-8")

    docx_path = None
    if DOCX_AVAILABLE:
        docx_path = SUMMARIES / f"{base}.docx"
        save_prediction_docx(pred, docx_path)

    cip_path = CIP_EXPORT_DIR / f"{base}.json"
    shutil.copy2(json_path, cip_path)
    write_manifest(pred, json_path, docx_path, cip_path)
    return json_path, docx_path, cip_path


def save_backtest(bt: Dict[str, Any]) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    game_file = safe_file_name(bt["summary"]["game"])
    path = BACKTEST_DIR / f"Theresa_Backtest_{game_file}_{ts}.json"
    path.write_text(json.dumps(to_json_safe(bt), indent=2), encoding="utf-8")
    return path


def print_prediction(pred: Dict[str, Any], json_path: Path, docx_path: Optional[Path], cip_path: Path) -> None:
    print("\n" + "=" * 70)
    print("THERESA MACHINE-AWARE HYBRID PREDICTOR v4.0")
    print("=" * 70)
    print(f"Game: {pred['game']}")
    print(f"Machine Family: {pred.get('machine_family')}")
    print(f"Strategy: {pred.get('strategy')}")
    print(f"Confidence: {pred.get('confidence')}")
    print("-" * 70)
    print("Banker:", f"{pred['banker']:02d}" if pred.get("banker") else "None")
    print("Top 2 :", nums_text(pred.get("top2", [])))
    print("Top 5 :", nums_text(pred.get("top5", [])))
    print("Top 10:", nums_text(pred.get("top10", [])))
    print("Top 20:", nums_text(pred.get("top20", [])))
    print("Top 30:", nums_text(pred.get("top30", [])))
    print("Top 60:", nums_text(pred.get("top60", [])))
    print("-" * 70)
    print("Saved JSON :", json_path)
    if docx_path:
        print("Saved DOCX :", docx_path)
    print("CIP Export :", cip_path)
    print("Manifest   :", MANIFEST_FILE)
    print("=" * 70)


def print_backtest(bt: Dict[str, Any], path: Path) -> None:
    s = bt["summary"]
    print("\nBACKTEST RESULTS")
    print("=" * 70)
    print(f"Engine: {s['engine_name']}")
    print(f"Game: {s['game']}")
    print(f"Machine Family: {s.get('machine_family')}")
    print(f"Test draws: {s['test_draws']}")
    print(f"Banker hit rate: {s['banker_rate']:.3f}")
    print(f"Top2 hit rate: {s['top2_rate']:.3f}")
    print(f"Top5 hit rate: {s['top5_rate']:.3f}")
    print(f"Top10 hit rate: {s['top10_rate']:.3f}")
    print(f"Top20 hit rate: {s['top20_rate']:.3f}")
    print(f"Top30 hit rate: {s['top30_rate']:.3f}")
    print(f"Top60 hit rate: {s['top60_rate']:.3f}")
    print(f"Saved: {path}")
    print("=" * 70)


def print_available_games(all_draws: Dict[str, List[Dict[str, Any]]]) -> None:
    print("\nAVAILABLE GAMES")
    print("=" * 70)
    for game in sorted(all_draws):
        print(f"{game:22} | {machine_family(game):12} | {len(all_draws[game])} draws")
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="Theresa Machine-Aware Hybrid Predictor v4.0")
    parser.add_argument("--target", "--game", dest="target", type=str, default=DEFAULT_TARGET_GAME)
    parser.add_argument("--backtest", action="store_true")
    parser.add_argument("--min-train", type=int, default=40)
    parser.add_argument("--list-games", action="store_true")
    parser.add_argument("--trigger-depth", type=int, default=3)
    parser.add_argument("--min-consistency", type=int, default=2)
    parser.add_argument(
        "--source-mode",
        type=str,
        default="auto",
        choices=["auto", "old15", "new4", "new4_plus_old_support", "all_except_target"],
    )
    parser.add_argument("--lookback", type=int, default=0, help="0 = all available history. New-machine auto uses 80 if 0.")

    args = parser.parse_args()
    target_game = normalize_game_name(args.target)

    logger.info("Loading canonical master data via engine_data_service")
    all_draws = load_all_games()

    if not all_draws:
        logger.error("No historical data loaded.")
        sys.exit(1)

    if args.list_games:
        print_available_games(all_draws)
        return

    if target_game not in all_draws:
        logger.error("Target game '%s' not found.", target_game)
        print_available_games(all_draws)
        sys.exit(1)

    if args.backtest:
        bt = theresa_backtest(
            all_draws=all_draws,
            target_game=target_game,
            min_train=args.min_train,
            source_mode=args.source_mode,
            lookback=args.lookback,
            trigger_depth=args.trigger_depth,
            min_consistency=args.min_consistency,
        )
        if not bt:
            logger.error("Backtest produced no result.")
            return

        path = save_backtest(bt)
        print_backtest(bt, path)
        return

    pred = theresa_predict(
        all_draws=all_draws,
        target_game=target_game,
        source_mode=args.source_mode,
        lookback=args.lookback,
        trigger_depth=args.trigger_depth,
        min_consistency=args.min_consistency,
    )
    pred["data_source"] = "engine_data_service"
    pred["dataset_sha256"] = canonical_dataset_checksum(all_draws)

    json_path, docx_path, cip_path = save_prediction(pred)
    print_prediction(pred, json_path, docx_path, cip_path)


if __name__ == "__main__":
    main()
