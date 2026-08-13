#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KADIJA ENGINE v4 — TOC PRODUCTION INTEGRATION
================================================
- Uses engine_data_service.py as the sole historical-data gateway
- Consumes validated canonical normalized_master_data.json indirectly
- Preserves canonical chronological order and draw positions
- Does not impose a duplicate-number rule beyond the canonical dataset
- Keeps Kadija v4 prediction logic intact
- Produces full TOP60, TOP30, TOP20, TOP10, TOP5, TOP2 and banker
"""

from __future__ import annotations

import json
import logging
import re
import sys
import os
import hashlib
import time
import shutil
import random
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from functools import lru_cache

import numpy as np
import pandas as pd

from engine_data_service import get_data_service, DataServiceError

try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

# ======================== FIXED RANDOM SEEDS ========================
random.seed(7)
np.random.seed(7)

# ======================== CONFIGURATION ========================
RUN_TYPE = os.getenv("RUN_TYPE", "prediction")

ENGINE_NAME = "kadija"
ENGINE_VERSION = "4.0"
ENGINE_ID = f"{ENGINE_NAME}_v4"

FIELD_MIN, FIELD_MAX = 1, 90
TOTAL_NUMBERS = 90
MIN_DRAWS_REQ = 20
REC_WIN = 6
OVER_MIN, OVER_MAX = 28, 80
POS_MIN = 12
PAIR_WIN = 110
COUNTER_WIN = 130

DEFAULT_ENSEMBLE_WEIGHTS = {
    "recency": 1.0,
    "gap": 1.0,
    "follow": 1.2,
    "combined": 1.5,
}

FIXED_BLEND = {
    "prior": 0.20,
    "momentum": 0.26,
    "position": 0.05,
    "micro": 0.10,
    "overdue": 0.06,
    "follow1": 0.09,
    "struct_pair": 0.06,
    "struct_counter": 0.06,
}

LEARNING_COOLDOWN = 3600
MIN_NEW_ROWS = 3
MIN_DRAWS_FOR_TUNING = 100
TUNING_TRIALS = 60
TUNING_LAST = 120
IMPROVEMENT_THRESHOLD = 0.01

MIN_CONFIDENCE = 0.0
MAX_CONFIDENCE = 1.0

# ======================== STANDARDIZED GAME REGISTRY ========================
GAMES = {
    1: {"name": "Monday special", "file": "monday special.csv"},
    2: {"name": "Wednesday midweek", "file": "wednesday midweek.csv"},
    3: {"name": "Friday bonanza", "file": "friday bonanza.csv"},
    4: {"name": "Saturday national", "file": "saturday national.csv"},
    5: {"name": "Sunday aseda", "file": "sunday aseda.csv"},
    6: {"name": "vag Monday", "file": "vag monday.csv"},
    7: {"name": "noon Monday", "file": "noon monday.csv"},
    8: {"name": "vag Tuesday", "file": "vag tuesday.csv"},
    9: {"name": "noon Tuesday", "file": "noon tuesday.csv"},
    10: {"name": "lucky Tuesday", "file": "lucky tuesday.csv"},
    11: {"name": "vag Wednesday", "file": "vag wednesday.csv"},
    12: {"name": "noon Wednesday", "file": "noon wednesday.csv"},
    13: {"name": "vag Thursday", "file": "vag thursday.csv"},
    14: {"name": "noon Thursday", "file": "noon thursday.csv"},
    15: {"name": "fortune Thursday", "file": "fortune thursday.csv"},
    16: {"name": "vag Friday", "file": "vag friday.csv"},
    17: {"name": "noon Friday", "file": "noon friday.csv"},
    18: {"name": "vag Saturday", "file": "vag saturday.csv"},
    19: {"name": "noon saturday", "file": "noon saturday.csv"},
}
GAME_REGISTRY = {v["name"]: k for k, v in GAMES.items()}

# ======================== PATHS ========================
HOME = Path.home()
DOCS = HOME / "Documents"
MASTER_DOCX = DOCS / "MASTER_DATA"
MASTER_CSV = DOCS / "MASTER_DATA_CSV"
ROOT = DOCS / "Kadija_Predictor"
SUMMARIES = ROOT / "summaries"
LOGS = ROOT / "logs"
PERF = ROOT / "performance"
BT_DIR = PERF / "backtest"
MODELS = ROOT / "models"
CONSENSUS_OUT = DOCS / "Consensus_Predictor" / "Fusion_Memory" / "input_streams" / ENGINE_NAME
LEO_CLEAN = DOCS / "Leo_Analyzer" / "clean_data"

for p in [ROOT, SUMMARIES, LOGS, PERF, BT_DIR, MODELS, CONSENSUS_OUT, LEO_CLEAN, MASTER_DOCX, MASTER_CSV]:
    p.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - KADIJA - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOGS / "kadija.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("KADIJA")

# ======================== TIME ========================
def utc_now():
    return datetime.now(timezone.utc)


def get_timestamp():
    return utc_now().strftime("%Y%m%d_%H%M%S")


def get_iso():
    return utc_now().isoformat()

# ======================== UTILITIES ========================
def safe_name(text: str) -> str:
    return re.sub(r"[^\w\s-]", "", text).strip().replace(" ", "_")


def get_game_id(name: str) -> Optional[int]:
    if not name:
        return None
    low = name.strip().lower()
    for n, gid in GAME_REGISTRY.items():
        if n.lower() == low:
            return gid
    return None


def _fmt(nums):
    return " ".join(f"{int(n):02d}" for n in nums) if nums else "None"


def add_positions(nums):
    return [{"number": int(n), "position": i + 1} for i, n in enumerate(nums)]

# ======================== CANONICAL TOC DATA LOADING ========================
# Historical data comes exclusively from engine_data_service.py.
# Kadija never reads MASTER_DATA DOCX/CSV directly.

def load_game_df(game_name: str, game_file: str = None) -> pd.DataFrame:
    """Load canonical chronological draws through the TOC data service."""
    try:
        service = get_data_service()
        canonical = service.canonical_game_name(game_name)
        records = service.records(canonical)
    except (DataServiceError, ValueError, TypeError) as exc:
        logger.error(f"Canonical data load failed for {game_name}: {exc}")
        return pd.DataFrame()

    if not records:
        logger.warning(f"{game_name}: canonical data service returned no records")
        return pd.DataFrame()

    # Preserve draw position and canonical chronological order exactly.
    rows = [list(record.draw_numbers) for record in records]
    df = pd.DataFrame(rows, columns=["N1", "N2", "N3", "N4", "N5"])
    df.attrs["canonical_game"] = canonical
    df.attrs["dataset_sha256"] = service.dataset_sha256()
    df.attrs["latest_draw_date"] = service.latest(canonical).iso_date
    logger.info(
        f"{canonical}: loaded {len(df)} canonical draws via engine_data_service "
        f"(latest={df.attrs['latest_draw_date']})"
    )
    return df


def draws_from_df(df: pd.DataFrame) -> List[List[int]]:
    """Convert the canonical frame to draws without inventing uniqueness rules."""
    if df.empty or df.shape[1] < 5:
        return []
    draws: List[List[int]] = []
    for _, row in df[["N1", "N2", "N3", "N4", "N5"]].iterrows():
        try:
            nums = [int(row["N1"]), int(row["N2"]), int(row["N3"]), int(row["N4"]), int(row["N5"])]
        except (TypeError, ValueError):
            continue
        if len(nums) == 5 and all(FIELD_MIN <= n <= FIELD_MAX for n in nums):
            draws.append(nums)
    return draws


def compute_checksum(df: pd.DataFrame) -> Optional[str]:
    """Stable checksum of the exact engine-visible chronological draw matrix."""
    if df.empty:
        return None
    payload = df[["N1", "N2", "N3", "N4", "N5"]].to_csv(index=False, lineterminator="\n")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

# ======================== ENTROPY SCORE ========================
def entropy_score(draws: List[List[int]], window: int = 30) -> float:
    recent = draws[-window:] if len(draws) > window else draws
    flat = [n for d in recent for n in d]
    if not flat:
        return 0.0
    counts = Counter(flat)
    probs = np.array(list(counts.values())) / len(flat)
    return float(-np.sum(probs * np.log2(probs + 1e-9)))

# ======================== MODEL MANAGEMENT ========================
def get_game_model_paths(game_name: str):
    game_dir = MODELS / safe_name(game_name)
    return game_dir, game_dir / "active.json", game_dir / "history"


def load_active_model(game_name: str) -> dict:
    _, active_path, _ = get_game_model_paths(game_name)
    if active_path.exists():
        try:
            with open(active_path, encoding="utf-8") as f:
                model = json.load(f)
            model.setdefault("data_checksum", None)
            model.setdefault("data_rows", 0)
            model.setdefault("blend", FIXED_BLEND.copy())
            model.setdefault("ensemble_weights", DEFAULT_ENSEMBLE_WEIGHTS.copy())
            model.setdefault("validation_score", 0.0)
            model.setdefault("last_save", 0)
            model.setdefault("model_id", "default")
            return model
        except Exception:
            logger.warning(f"Corrupted model for {game_name}; resetting")
    return {
        "data_checksum": None,
        "data_rows": 0,
        "blend": FIXED_BLEND.copy(),
        "ensemble_weights": DEFAULT_ENSEMBLE_WEIGHTS.copy(),
        "validation_score": 0.0,
        "last_save": 0,
        "model_id": "default",
    }


def save_candidate_model(game_name: str, model: dict) -> Path:
    _, _, history = get_game_model_paths(game_name)
    history.mkdir(parents=True, exist_ok=True)
    if not model.get("model_id") or model["model_id"] == "default":
        model["model_id"] = f"{get_timestamp()}_{os.getpid()}"
    path = history / f"model_{model['model_id']}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(model, f, indent=2)
    return path


def promote_to_active(game_name: str, candidate_path: Path):
    _, active_path, _ = get_game_model_paths(game_name)
    active_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(candidate_path, active_path)


def acquire_learn_lock(game_name: str) -> bool:
    lock = MODELS / safe_name(game_name) / ".learn.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.exists():
        if time.time() - lock.stat().st_mtime > 7200:
            lock.unlink()
        else:
            return False
    with open(lock, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    return True


def release_learn_lock(game_name: str):
    lock = MODELS / safe_name(game_name) / ".learn.lock"
    lock.unlink(missing_ok=True)

# ======================== CORE SIGNALS ========================
def prior_from_draws(draws: List[List[int]]) -> Dict[int, float]:
    if not draws:
        return {n: 1.0 / TOTAL_NUMBERS for n in range(1, TOTAL_NUMBERS + 1)}
    c = Counter()
    for d in draws:
        c.update(d)
    T = len(draws)
    prior = {n: (c.get(n, 0) + 2) / (T + 180) for n in range(1, TOTAL_NUMBERS + 1)}
    s = sum(prior.values()) or 1.0
    return {n: prior[n] / s for n in prior}


def momentum(draws: List[List[int]], rk: int = 15, pk: int = 30) -> Dict[int, float]:
    if len(draws) < 10:
        return {n: 0.0 for n in range(1, TOTAL_NUMBERS + 1)}
    recent = draws[-rk:] if len(draws) > rk else draws
    prior_blk = draws[-(rk + pk):-rk] if len(draws) > (rk + 5) else []
    rc = Counter(n for d in recent for n in d)
    pc = Counter(n for d in prior_blk for n in d) if prior_blk else Counter()
    raw = {}
    for n in range(1, TOTAL_NUMBERS + 1):
        r = rc.get(n, 0) / max(1.0, len(recent))
        p = pc.get(n, 0) / max(1.0, len(prior_blk)) if prior_blk else 0.0
        raw[n] = max(0.0, r - p)
    m = max(raw.values()) or 1.0
    return {n: raw[n] / m for n in raw}


def position(draws: List[List[int]]) -> Dict[int, float]:
    if len(draws) < POS_MIN:
        return {n: 0.0 for n in range(1, TOTAL_NUMBERS + 1)}
    pos = [Counter() for _ in range(5)]
    for d in draws:
        for i, n in enumerate(d):
            pos[i][n] += 1
    T = len(draws)
    expected = T / TOTAL_NUMBERS
    out = {}
    for n in range(1, TOTAL_NUMBERS + 1):
        best = max((pos[i].get(n, 0) / expected for i in range(5)), default=0.0)
        out[n] = best
    m = max(out.values()) or 1.0
    return {n: out[n] / m for n in out}


def micro(draws: List[List[int]], win: int = REC_WIN) -> Dict[int, float]:
    recent = draws[-win:] if len(draws) > win else draws
    present = set(n for d in recent for n in d)
    return {n: (1.0 if n in present else 0.0) for n in range(1, TOTAL_NUMBERS + 1)}


def overdue(draws: List[List[int]], mn: int = OVER_MIN, mx: int = OVER_MAX) -> Dict[int, float]:
    last = {n: None for n in range(1, TOTAL_NUMBERS + 1)}
    for i, d in enumerate(draws):
        for n in d:
            last[n] = i
    L = len(draws) - 1
    out = {}
    for n in range(1, TOTAL_NUMBERS + 1):
        ls = last[n]
        gap = (L - ls) if ls is not None else mx
        if gap < mn:
            s = 0.0
        elif gap >= mx:
            s = 1.0
        else:
            s = (gap - mn) / (mx - mn)
        out[n] = s
    m = max(out.values()) or 1.0
    return {n: out[n] / m for n in out}


def follow1_map(draws: List[List[int]]) -> defaultdict:
    one = defaultdict(Counter)
    for i in range(1, len(draws)):
        for x in draws[i - 1]:
            for y in draws[i]:
                one[x][y] += 1
    for x in list(one.keys()):
        m = max(one[x].values()) if one[x] else 1.0
        for y in list(one[x].keys()):
            one[x][y] /= m
    return one


def pair_map(draws: List[List[int]], window: int = PAIR_WIN) -> defaultdict:
    hist = draws[-window:] if len(draws) > window else draws
    co = defaultdict(Counter)
    for d in hist:
        for i in range(5):
            for j in range(i + 1, 5):
                a, b = d[i], d[j]
                co[a][b] += 1
                co[b][a] += 1
    return co


def counter_map(draws: List[List[int]], window: int = COUNTER_WIN) -> defaultdict:
    hist = draws[-window:] if len(draws) > window else draws
    one = defaultdict(Counter)
    for i in range(1, len(hist)):
        prev, curr = set(hist[i - 1]), set(hist[i])
        for x in prev:
            for y in curr:
                one[x][y] += 1
    for x in list(one.keys()):
        m = max(one[x].values()) if one[x] else 1.0
        for y in list(one[x].keys()):
            one[x][y] /= m
    return one

# ======================== ENSEMBLE STRATEGIES ========================
def strategy_recency(draws: List[List[int]]) -> List[int]:
    recent = draws[-20:] if len(draws) >= 20 else draws
    c = Counter(n for d in recent for n in d)
    return [n for n, _ in c.most_common(10)]


def strategy_gap(draws: List[List[int]]) -> List[int]:
    last_seen = {}
    for i, d in enumerate(draws):
        for n in d:
            last_seen[n] = i
    L = len(draws)
    gap = {n: L - last_seen.get(n, -1) for n in range(1, TOTAL_NUMBERS + 1)}
    return [n for n, _ in sorted(gap.items(), key=lambda x: x[1], reverse=True)[:10]]


def strategy_follow(draws: List[List[int]]) -> List[int]:
    fmap = follow1_map(draws)
    last = set(draws[-1]) if draws else set()
    c = Counter()
    for x in last:
        for y, score in fmap.get(x, {}).items():
            if y not in last:
                c[y] += score
    return [n for n, _ in c.most_common(10)]


def strategy_combined_top10(draws: List[List[int]], blend: Dict[str, float]) -> List[int]:
    scores = combined(draws, blend)
    return [n for n, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10]]

# ======================== BANKER STABILIZER ========================
def select_banker(top5: List[int], scores: Dict[int, float], draws: List[List[int]]) -> Optional[int]:
    if not top5:
        return None
    mom = momentum(draws)
    mic = micro(draws)
    ovd = overdue(draws)
    final = {}
    for rank, n in enumerate(top5):
        rank_bonus = (5 - rank) * 0.03
        final[n] = (
            scores.get(n, 0) * 0.55
            + mom.get(n, 0) * 0.20
            + mic.get(n, 0) * 0.15
            + ovd.get(n, 0) * 0.10
            + rank_bonus
        )
    return max(final, key=final.get)

# ======================== ENSEMBLE VOTING SYSTEM ========================
def ensemble_predict(draws: List[List[int]], blend: Dict[str, float], ensemble_weights: Dict[str, float]) -> Dict[str, object]:
    votes = Counter()
    presence = defaultdict(int)

    rec = strategy_recency(draws)
    gap = strategy_gap(draws)
    fol = strategy_follow(draws)
    comb = strategy_combined_top10(draws, blend)

    for label, nums in [("recency", rec), ("gap", gap), ("follow", fol), ("combined", comb)]:
        for n in nums:
            votes[n] += ensemble_weights.get(label, DEFAULT_ENSEMBLE_WEIGHTS.get(label, 1.0))
            presence[n] += 1

    for n in list(votes.keys()):
        votes[n] += presence[n] * 0.5

    last_draw = set(draws[-1]) if draws else set()
    ranked = sorted(
        votes.keys(),
        key=lambda n: (votes[n] - (0.3 if n in last_draw else 0), -n),
        reverse=True,
    )

    top10 = []
    decade_count = Counter()
    for n in ranked:
        dec = (n - 1) // 10
        if decade_count[dec] >= 3:
            continue
        top10.append(n)
        decade_count[dec] += 1
        if len(top10) == 10:
            break

    # Fill if decade cap leaves fewer than 10
    if len(top10) < 10:
        for n in ranked:
            if n not in top10:
                top10.append(n)
            if len(top10) == 10:
                break

    top5 = top10[:5]
    top2 = top5[:2]
    return {"top10": top10, "top5": top5, "top2": top2, "ranked_votes": ranked, "votes": dict(votes.most_common(20))}

# ======================== STRATEGY PERFORMANCE LEARNING ========================
def evaluate_strategies(draws: List[List[int]], blend: Dict[str, float]) -> Dict[str, float]:
    results = {"recency": 0, "gap": 0, "follow": 0, "combined": 0}
    count = 0
    for i in range(30, len(draws) - 1):
        hist = draws[:i]
        actual = set(draws[i])
        if len(set(strategy_recency(hist)[:5]) & actual) >= 2:
            results["recency"] += 1
        if len(set(strategy_gap(hist)[:5]) & actual) >= 2:
            results["gap"] += 1
        if len(set(strategy_follow(hist)[:5]) & actual) >= 2:
            results["follow"] += 1
        if len(set(strategy_combined_top10(hist, blend)[:5]) & actual) >= 2:
            results["combined"] += 1
        count += 1
    if count == 0:
        return DEFAULT_ENSEMBLE_WEIGHTS.copy()
    weights = {k: max(v / count, 0.05) for k, v in results.items()}
    total = sum(weights.values())
    if total > 0:
        weights = {k: (v / total) * 4.0 for k, v in weights.items()}
    logger.info(f"Learned weights pre-validation: {weights}")
    return weights


def score_ensemble(draws: List[List[int]], blend: Dict[str, float], weights: Dict[str, float], window: int = 60) -> float:
    hits = 0
    total = 0
    start = max(30, len(draws) - window)
    for i in range(start, len(draws) - 1):
        hist = draws[:i]
        actual = set(draws[i])
        ensemble = ensemble_predict(hist, blend, weights)
        if len(set(ensemble["top5"]) & actual) >= 2:
            hits += 1
        total += 1
    return hits / total if total > 0 else 0.0

# ======================== COMBINED SCORING ========================
@lru_cache(maxsize=256)
def _combined_cached(draws_key: Tuple[Tuple[int, ...], ...], blend_key: Tuple[Tuple[str, float], ...]) -> Dict[int, float]:
    draws = [list(d) for d in draws_key]
    blend = dict(blend_key)

    prior = prior_from_draws(draws)
    mom = momentum(draws)
    pos = position(draws)
    mic = micro(draws)
    ovd = overdue(draws)
    fmap = follow1_map(draws)

    last_set = set(draws[-1]) if draws else set()
    fol = Counter()
    for x in last_set:
        fol.update(fmap.get(x, Counter()))

    score = {}
    for n in range(1, TOTAL_NUMBERS + 1):
        s = (
            blend["prior"] * prior.get(n, 0)
            + blend["momentum"] * mom.get(n, 0)
            + blend["position"] * pos.get(n, 0)
            + blend["micro"] * mic.get(n, 0)
            + blend["overdue"] * ovd.get(n, 0)
            + blend["follow1"] * fol.get(n, 0)
        )
        score[n] = s

    mx = max(score.values()) or 1.0
    for n in score:
        score[n] /= mx

    pm = pair_map(draws)
    cm = counter_map(draws)
    seeds = [n for n, _ in sorted(score.items(), key=lambda x: x[1], reverse=True)[:12]]

    pair_b = Counter()
    count_b = Counter()
    for n in seeds:
        for y, _ in pm.get(n, Counter()).most_common(1):
            if y != n:
                pair_b[y] += 1
        for y, _ in cm.get(n, Counter()).most_common(1):
            if y != n:
                count_b[y] += 1

    def _norm(c: Counter) -> Dict[int, float]:
        if not c:
            return {}
        m = max(c.values()) or 1
        return {k: c[k] / m for k in c}

    pair_b_norm = _norm(pair_b)
    count_b_norm = _norm(count_b)

    boosted = {}
    for n in range(1, TOTAL_NUMBERS + 1):
        boosted[n] = score.get(n, 0) + blend["struct_pair"] * pair_b_norm.get(n, 0) + blend["struct_counter"] * count_b_norm.get(n, 0)

    mx2 = max(boosted.values()) or 1.0
    for n in boosted:
        boosted[n] /= mx2
    return boosted


def combined(draws: List[List[int]], blend: Dict[str, float]) -> Dict[int, float]:
    draws_key = tuple(tuple(d) for d in draws)
    blend_key = tuple(sorted(blend.items()))
    return _combined_cached(draws_key, blend_key)

# ======================== TUNING ========================
def _normalize_blend(bl: Dict[str, float]) -> Dict[str, float]:
    s = sum(bl.values()) or 1.0
    return {k: v / s for k, v in bl.items()}


def _rand_blend_around(base: Dict[str, float], jitter: float = 0.25) -> Dict[str, float]:
    out = {}
    for k, v in base.items():
        mult = random.uniform(1.0 - jitter, 1.0 + jitter)
        out[k] = max(0.001, v * mult)
    return _normalize_blend(out)


def _score_summary(summary: Dict[str, float]) -> float:
    return (
        summary["top5_2plus_rate"] * 0.40
        + summary["banker_hit_rate"] * 0.20
        + summary["top20_3plus_rate"] * 0.20
        + summary["top30_4plus_rate"] * 0.20
    )


def backtest_blend(draws: List[List[int]], blend: Dict[str, float], last: int = TUNING_LAST) -> Dict[str, float]:
    if len(draws) < MIN_DRAWS_FOR_TUNING:
        return {"samples": 0, "top5_2plus_rate": 0.0, "banker_hit_rate": 0.0, "top20_3plus_rate": 0.0, "top30_4plus_rate": 0.0}
    start = max(MIN_DRAWS_REQ, len(draws) - last)
    rows = []
    for t in range(start, len(draws)):
        hist = draws[:t]
        target = set(draws[t])
        scores = combined(hist, blend)
        ranked = [n for n, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)]
        top5 = ranked[:5]
        top20 = ranked[:20]
        top30 = ranked[:30]
        banker = select_banker(top5, scores, hist) if top5 else None
        rows.append({
            "top5_hits": len(target & set(top5)),
            "top20_hits": len(target & set(top20)),
            "top30_hits": len(target & set(top30)),
            "banker_hit": 1 if banker in target else 0,
        })
    samples = len(rows)
    if samples == 0:
        return {"samples": 0, "top5_2plus_rate": 0.0, "banker_hit_rate": 0.0, "top20_3plus_rate": 0.0, "top30_4plus_rate": 0.0}
    return {
        "samples": samples,
        "top5_2plus_rate": sum(1 for r in rows if r["top5_hits"] >= 2) / samples,
        "banker_hit_rate": sum(r["banker_hit"] for r in rows) / samples,
        "top20_3plus_rate": sum(1 for r in rows if r["top20_hits"] >= 3) / samples,
        "top30_4plus_rate": sum(1 for r in rows if r["top30_hits"] >= 4) / samples,
    }


def tune_game(game_name: str, draws: List[List[int]], fixed_blend: Dict[str, float] = FIXED_BLEND, trials: int = TUNING_TRIALS, last: int = TUNING_LAST):
    random.seed(7)
    best_blend = fixed_blend.copy()
    base_summary = backtest_blend(draws, fixed_blend, last)
    best_score = _score_summary(base_summary)
    for i in range(trials):
        jitter = 0.3 if i < trials * 0.6 else 0.15
        cand = _rand_blend_around(fixed_blend, jitter=jitter)
        summ = backtest_blend(draws, cand, last)
        sc = _score_summary(summ)
        if sc > best_score + IMPROVEMENT_THRESHOLD:
            best_score, best_blend = sc, cand
            logger.info(f"{game_name}: new best blend score={best_score:.3f} trial={i}")
    return best_blend, best_score, base_summary

# ======================== PREDICTION & LEARNING ========================
def predict_for_game(game_name: str, df: pd.DataFrame) -> Optional[dict]:
    draws = draws_from_df(df)
    if len(draws) < MIN_DRAWS_REQ:
        logger.warning(f"{game_name}: insufficient draws ({len(draws)})")
        return None

    model = load_active_model(game_name)
    new_checksum = compute_checksum(df)
    old_checksum = model.get("data_checksum")
    old_rows = int(model.get("data_rows", 0) or 0)
    new_rows = len(df)

    data_changed = new_checksum != old_checksum

    if data_changed and new_rows > old_rows and (new_rows - old_rows) >= MIN_NEW_ROWS and new_rows >= MIN_DRAWS_FOR_TUNING:
        if acquire_learn_lock(game_name):
            try:
                logger.info(f"{game_name}: data changed ({old_rows}→{new_rows}), tuning...")
                best_blend, best_score, base_summary = tune_game(game_name, draws)
                _combined_cached.cache_clear()
                if best_score > _score_summary(base_summary) + IMPROVEMENT_THRESHOLD:
                    model["blend"] = best_blend
                    model["validation_score"] = min(MAX_CONFIDENCE, max(MIN_CONFIDENCE, best_score))
                    model["model_id"] = f"{get_timestamp()}_{os.getpid()}"
                    logger.info(f"{game_name}: improved to validation_score {best_score:.4f}")
                else:
                    logger.info(f"{game_name}: no improvement, keeping current blend")
                model["data_checksum"] = new_checksum
                model["data_rows"] = new_rows
                model["last_learn"] = time.time()
                candidate = save_candidate_model(game_name, model)
                promote_to_active(game_name, candidate)
            except Exception as e:
                logger.error(f"{game_name}: tuning failed: {e}")
            finally:
                release_learn_lock(game_name)
        else:
            logger.info(f"{game_name}: learning lock active; updating checksum only")
            model["data_checksum"] = new_checksum
            model["data_rows"] = new_rows
            candidate = save_candidate_model(game_name, model)
            promote_to_active(game_name, candidate)
    elif data_changed:
        model["data_checksum"] = new_checksum
        model["data_rows"] = new_rows
        candidate = save_candidate_model(game_name, model)
        promote_to_active(game_name, candidate)

    if RUN_TYPE != "prediction":
        return {"trained": True}

    model = load_active_model(game_name)
    blend = model.get("blend", FIXED_BLEND).copy()

    ent = entropy_score(draws)
    if ent > 5.7:
        blend["momentum"] *= 1.20
        blend["micro"] *= 1.15
        blend["follow1"] *= 1.10
    elif ent < 5.1:
        blend["prior"] *= 1.20
        blend["position"] *= 1.15
        blend["overdue"] *= 1.10
    blend = _normalize_blend(blend)

    if len(draws) > 80 and data_changed and new_rows > old_rows:
        old_weights = model.get("ensemble_weights", DEFAULT_ENSEMBLE_WEIGHTS)
        learned_weights = evaluate_strategies(draws, blend)
        old_score = score_ensemble(draws, blend, old_weights)
        new_score = score_ensemble(draws, blend, learned_weights)
        if new_score > old_score + 0.01:
            logger.info(f"IMPROVED ensemble weights: {old_score:.3f} → {new_score:.3f}")
            model["ensemble_weights"] = learned_weights
        else:
            logger.info(f"REJECTED new weights: {new_score:.3f} <= {old_score:.3f}+0.01")
        candidate = save_candidate_model(game_name, model)
        promote_to_active(game_name, candidate)

    ensemble_weights = model.get("ensemble_weights", DEFAULT_ENSEMBLE_WEIGHTS)
    model["ensemble_weights"] = ensemble_weights

    _combined_cached.cache_clear()
    scores = combined(draws, blend)
    if not scores:
        logger.error("Empty score set — aborting prediction")
        return None

    ranked = [n for n, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)]
    top60 = ranked[:60]
    top30 = top60[:30]
    top20 = top60[:20]

    ensemble = ensemble_predict(draws, blend, ensemble_weights)
    top10 = ensemble["top10"]
    top5 = ensemble["top5"]
    top2 = ensemble["top2"]
    banker = select_banker(top5, scores, draws)
    vote_strength = sum(ensemble["votes"].get(n, 0) for n in top5) / max(1.0, len(top5))

    return {
        "top60": top60,
        "top30": top30,
        "top20": top20,
        "top10": top10,
        "top5": top5,
        "top2": top2,
        "banker": banker,
        "confidence": min(MAX_CONFIDENCE, max(MIN_CONFIDENCE, float(model.get("validation_score", 0.0) or 0.0))),
        "ensemble_confidence": round(float(vote_strength), 4),
        "ensemble_weights": model.get("ensemble_weights", DEFAULT_ENSEMBLE_WEIGHTS),
        "data_source": "TOC_ENGINE_DATA_SERVICE",
    }

# ======================== OUTPUT HELPERS ========================
def save_pred_json(game_name: str, pred: dict):
    gid = get_game_id(game_name)
    ts = get_timestamp()
    safe = safe_name(game_name)
    filename = f"ENGINE_{ENGINE_ID}_{safe}_{ts}_{os.getpid()}.json"
    out_path = CONSENSUS_OUT / filename
    model = load_active_model(game_name)
    payload = {
        "engine": ENGINE_NAME,
        "engine_id": ENGINE_ID,
        "game": game_name,
        "game_id": gid,
        "run_type": "prediction",
        "date": utc_now().strftime("%Y-%m-%d"),
        "generated": get_iso(),
        "model_id": model.get("model_id", "unknown"),
        "data_checksum": model.get("data_checksum"),
        "data_source": pred.get("data_source"),
        "ensemble_weights": model.get("ensemble_weights", DEFAULT_ENSEMBLE_WEIGHTS),
        "top60": add_positions(pred["top60"]),
        "top30": add_positions(pred["top30"]),
        "top20": add_positions(pred["top20"]),
        "top10": add_positions(pred["top10"]),
        "top5": add_positions(pred["top5"]),
        "top2": add_positions(pred["top2"]),
        "banker": pred["banker"],
        "confidence": pred.get("confidence", 0.0),
        "ensemble_confidence": pred.get("ensemble_confidence", 0.0),
        "meta": {"top60_size": len(pred["top60"]), "top10_size": len(pred["top10"])},
    }
    tmp = out_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, out_path)
    logger.info(f"Fusion JSON saved: {out_path}")


def save_pred_docx(game_name: str, pred: dict):
    if not DOCX_AVAILABLE:
        logger.warning("DOCX module not installed — skipping DOCX output")
        return
    ts = get_timestamp()
    safe = safe_name(game_name)
    path = SUMMARIES / f"ENGINE_{ENGINE_ID}_{safe}_{ts}.docx"
    doc = Document()
    doc.add_heading(f"{ENGINE_NAME.upper()} ENGINE v4 — {game_name}", 0)
    doc.add_paragraph(f"Generated: {get_iso()}")
    doc.add_paragraph(f"Data source: {pred.get('data_source')}")
    doc.add_paragraph(f"Confidence: {pred['confidence']:.4f}")
    doc.add_paragraph(f"Ensemble Confidence: {pred.get('ensemble_confidence', 0.0):.4f}")
    doc.add_heading("STRATEGY WEIGHTS", level=1)
    for strat, weight in pred.get("ensemble_weights", {}).items():
        doc.add_paragraph(f"{strat}: {weight:.2f}")
    doc.add_heading("PREDICTIONS", level=1)
    for title, key in [("TOP 60", "top60"), ("TOP 30", "top30"), ("TOP 20", "top20"), ("TOP 10", "top10"), ("TOP 5", "top5"), ("TOP 2", "top2")]:
        doc.add_heading(title, level=2)
        doc.add_paragraph(_fmt(pred[key]))
    doc.add_heading("BANKER", level=2)
    doc.add_paragraph(f"{pred['banker']:02d}" if pred["banker"] else "None")
    doc.save(path)
    logger.info(f"DOCX saved: {path}")


def save_pred_leo(game_name: str, pred: dict):
    safe = safe_name(game_name)
    folder = LEO_CLEAN / safe
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{ENGINE_NAME}_{get_timestamp()}_{os.getpid()}.json"
    model = load_active_model(game_name)
    payload = {
        "engine": ENGINE_NAME,
        "engine_id": ENGINE_ID,
        "game": game_name,
        "game_id": get_game_id(game_name),
        "run_type": "prediction",
        "date": utc_now().strftime("%Y-%m-%d"),
        "generated": get_iso(),
        "data_source": pred.get("data_source"),
        "ensemble_weights": model.get("ensemble_weights", DEFAULT_ENSEMBLE_WEIGHTS),
        "top60": add_positions(pred["top60"]),
        "top30": add_positions(pred["top30"]),
        "top20": add_positions(pred["top20"]),
        "top10": add_positions(pred["top10"]),
        "top5": add_positions(pred["top5"]),
        "top2": add_positions(pred["top2"]),
        "banker": pred["banker"],
        "confidence": pred.get("confidence", 0.0),
        "ensemble_confidence": pred.get("ensemble_confidence", 0.0),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    logger.info(f"Leo output saved: {path}")

# ======================== MAIN ========================
def main():
    _combined_cached.cache_clear()
    run_type = RUN_TYPE

    try:
        gid = int(sys.stdin.readline().strip())
    except Exception:
        print("Invalid game id")
        sys.exit(1)

    game_info = GAMES.get(gid)
    if not game_info:
        print("Invalid game id")
        sys.exit(1)

    df = load_game_df(game_info["name"])
    if df.empty:
        print("No data")
        sys.exit(1)

    pred = predict_for_game(game_info["name"], df)

    if run_type != "prediction":
        if pred:
            print("TRAINING COMPLETE")
        else:
            print("FAILED")
            sys.exit(1)
        sys.exit(0)

    required_keys = ["top60", "top30", "top20", "top10", "top5", "top2", "banker", "confidence"]
    if pred is None or not all(k in pred for k in required_keys):
        logger.error("Invalid prediction structure")
        print("FAILED")
        sys.exit(1)

    try:
        save_pred_docx(game_info["name"], pred)
        save_pred_json(game_info["name"], pred)
        save_pred_leo(game_info["name"], pred)
    except Exception as e:
        logger.error(f"Output failure: {e}")
        print("FAILED")
        sys.exit(1)

    print("DONE")
    sys.exit(0)


if __name__ == "__main__":
    main()
