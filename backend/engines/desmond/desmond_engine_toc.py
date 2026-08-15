#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
desmond_Engine.py — Desmond Engine V2 — TOC Integrated (LAUNCHER COMPATIBLE + PARSER FIXED)
============================================================================
- Compatible with master launcher: reads game_id from stdin and RUN_TYPE from environment.
- Supports prediction, training, and backtest.
- Prints DONE / TRAINING COMPLETE / BACKTEST DONE for launcher success detection.
- TOC integrated: reads canonical historical draws only through engine_data_service.
- Preserves canonical chronological draw order and canonical draw values.
- Produces standardized TOC prediction complement: TOP60, TOP30, TOP20, TOP10, TOP5, TOP2, BANKER, CONFIDENCE.
- Outputs local DOCX summary and timestamped Consensus/Fusion input-stream JSON.
- Produces no Leo export and no auxiliary two-number-set prediction stream.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import shutil
import sys
import time
import hashlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    from engine_data_service import get_data_service, DataServiceError
except ImportError as exc:
    raise RuntimeError(
        "Desmond TOC requires backend/engine_data_service.py on PYTHONPATH"
    ) from exc

try:
    from docx import Document
    from docx.shared import Pt
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

# =============================================================================
# BASIC SETUP
# =============================================================================
random.seed(7)
np.random.seed(7)

ENGINE_NAME = "desmond"
ENGINE_ID = "desmond_v2"
FIELD_MIN, FIELD_MAX = 1, 90
MIN_DRAWS_REQ = 80
LEARNING_COOLDOWN = 180
PROMOTION_THRESHOLD = 0.01
RANDOM_SEARCH_SAMPLES = 200

HOME = Path.home()
DOCS = HOME / "Documents"
ROOT = DOCS / "Desmond_Predictor"
SUMMARIES = ROOT / "summaries"
LOGS = ROOT / "logs"
PERF = ROOT / "performance"
BT_DIR = PERF / "backtest"
MODELS = ROOT / "models"
CONSENSUS_OUT = DOCS / "Consensus_Predictor" / "Fusion_Memory" / "input_streams" / "Desmond_Engine"

for p in [ROOT, SUMMARIES, LOGS, PERF, BT_DIR, MODELS, CONSENSUS_OUT]:
    p.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - DESMOND - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOGS / "desmond.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("DESMOND")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# =============================================================================
# GAME REGISTRY
# =============================================================================
GAMES = {
    1:  {"name": "Monday special",     "file": "monday special.csv",     "machine": "new"},
    2:  {"name": "Wednesday midweek",  "file": "wednesday midweek.csv",  "machine": "new"},
    3:  {"name": "Friday bonanza",     "file": "friday bonanza.csv",     "machine": "new"},
    4:  {"name": "Saturday national",  "file": "saturday national.csv",  "machine": "new"},
    5:  {"name": "Sunday aseda",       "file": "sunday aseda.csv",       "machine": "old"},
    6:  {"name": "vag Monday",         "file": "vag monday.csv",         "machine": "old"},
    7:  {"name": "noon Monday",        "file": "noon monday.csv",        "machine": "old"},
    8:  {"name": "vag Tuesday",        "file": "vag tuesday.csv",        "machine": "old"},
    9:  {"name": "noon Tuesday",       "file": "noon tuesday.csv",       "machine": "old"},
    10: {"name": "lucky Tuesday",      "file": "lucky tuesday.csv",      "machine": "old"},
    11: {"name": "vag Wednesday",      "file": "vag wednesday.csv",      "machine": "old"},
    12: {"name": "noon Wednesday",     "file": "noon wednesday.csv",     "machine": "old"},
    13: {"name": "vag Thursday",       "file": "vag thursday.csv",       "machine": "old"},
    14: {"name": "noon Thursday",      "file": "noon thursday.csv",      "machine": "old"},
    15: {"name": "fortune Thursday",   "file": "fortune thursday.csv",   "machine": "old"},
    16: {"name": "vag Friday",         "file": "vag friday.csv",         "machine": "old"},
    17: {"name": "noon Friday",        "file": "noon friday.csv",        "machine": "old"},
    18: {"name": "vag Saturday",       "file": "vag saturday.csv",       "machine": "old"},
    19: {"name": "noon saturday",      "file": "noon saturday.csv",      "machine": "old"},
}

BASE_BLEND = {
    "prior": 0.55,
    "momentum": 0.22,
    "position": 0.10,
    "micro_recency": 0.07,
    "overdue": 0.06,
    "follow1": 0.02,
}

DEFAULT_HYPERPARAMS = {
    "momentum_recent": 15,
    "momentum_prior": 30,
    "overdue_min": 40,
    "overdue_max": 80,
    "recency_window": 10,
    "pair_window": 30,
}

MOMENTUM_RECENT_GRID = [10, 15, 20, 25, 30]
MOMENTUM_PRIOR_GRID = [20, 30, 40, 50, 60]
OVERDUE_MIN_GRID = [30, 40, 50, 60, 70]
OVERDUE_MAX_GRID = [60, 70, 80, 90, 100]
RECENCY_WINDOW_GRID = [5, 10, 15, 20, 25]
PAIR_WINDOW_GRID = [20, 30, 40, 50, 60]

# =============================================================================
# TOC CANONICAL DATA ADAPTER
# =============================================================================
def is_valid_draw(nums: List[int]) -> bool:
    """Validate the canonical 5-number shape without imposing uniqueness.

    The normalized TOC dataset is authoritative. Repeated values are preserved
    exactly when present in a validated canonical draw.
    """
    if len(nums) != 5:
        return False
    for x in nums:
        try:
            n = int(x)
        except Exception:
            return False
        if n < FIELD_MIN or n > FIELD_MAX:
            return False
    return True


def load_game_df(game_name: str, game_file: Optional[str] = None) -> pd.DataFrame:
    """Load one game's complete canonical history via engine_data_service."""
    del game_file  # legacy launcher metadata; no file-system parsing is performed
    try:
        service = get_data_service()
        records = service.records(game_name)
    except (DataServiceError, KeyError, ValueError, TypeError) as exc:
        logger.error("Canonical data load failed for %s: %s", game_name, exc)
        return pd.DataFrame()

    rows = [list(record.draw_numbers) for record in records]
    if not rows:
        logger.warning("No canonical draws available for %s", game_name)
        return pd.DataFrame()

    df = pd.DataFrame(
        rows,
        columns=["Number_1", "Number_2", "Number_3", "Number_4", "Number_5"],
    )
    logger.info(
        "%s: loaded %d canonical draws via engine_data_service (latest=%s)",
        game_name,
        len(df),
        records[-1].iso_date,
    )
    return df


def load_all_games() -> Dict[str, pd.DataFrame]:
    data: Dict[str, pd.DataFrame] = {}
    for info in GAMES.values():
        df = load_game_df(info["name"])
        if not df.empty:
            data[info["name"]] = df
    return data


def draws_from_df(df: pd.DataFrame) -> List[List[int]]:
    if df is None or df.empty or df.shape[1] < 5:
        return []
    draws: List[List[int]] = []
    for i in range(len(df)):
        try:
            nums = [int(df.iloc[i, j]) for j in range(5)]
        except Exception:
            continue
        if is_valid_draw(nums):
            draws.append(nums)
    return draws


def compute_checksum(df: pd.DataFrame) -> str:
    """Stable checksum for the exact engine-facing canonical draw matrix."""
    return (
        hashlib.sha256(df.to_csv(index=False).encode("utf-8")).hexdigest()
        if df is not None and not df.empty
        else ""
    )

# =============================================================================
# MODEL MANAGEMENT
# =============================================================================
def safe_name(name: str) -> str:
    return re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_")


def get_game_model_paths(game_name: str) -> Tuple[Path, Path, Path]:
    folder = MODELS / safe_name(game_name)
    return folder, folder / "active.json", folder / "history"


def default_model(game_name: str) -> Dict[str, Any]:
    return {
        "engine": "Desmond",
        "game": game_name,
        "model_id": "default",
        "created": utc_now().isoformat(),
        "blend": BASE_BLEND.copy(),
        "hyperparams": DEFAULT_HYPERPARAMS.copy(),
        "data_checksum": None,
        "data_rows": 0,
        "validation_score": 0.0,
        "last_learn": 0,
    }


def load_active_model(game_name: str) -> Dict[str, Any]:
    _, active, _ = get_game_model_paths(game_name)
    if active.exists():
        try:
            with open(active, "r", encoding="utf-8") as f:
                model = json.load(f)
            base = default_model(game_name)
            for k, v in base.items():
                model.setdefault(k, v)
            model.setdefault("hyperparams", DEFAULT_HYPERPARAMS.copy())
            for k, v in DEFAULT_HYPERPARAMS.items():
                model["hyperparams"].setdefault(k, v)
            return model
        except Exception as e:
            logger.warning("Failed to load active model for %s: %s", game_name, e)
    return default_model(game_name)


def save_candidate_model(game_name: str, model: Dict[str, Any]) -> Path:
    folder, _, history = get_game_model_paths(game_name)
    history.mkdir(parents=True, exist_ok=True)
    if not model.get("model_id") or model.get("model_id") == "default":
        model["model_id"] = utc_now().strftime("%Y%m%d_%H%M%S")
    path = history / f"model_{model['model_id']}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(model, f, indent=2)
    return path


def promote_to_active(game_name: str, candidate_path: Path) -> None:
    folder, active, _ = get_game_model_paths(game_name)
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(candidate_path, active)


def acquire_learn_lock(game_name: str) -> bool:
    folder, _, _ = get_game_model_paths(game_name)
    folder.mkdir(parents=True, exist_ok=True)
    lock = folder / ".learn.lock"
    if lock.exists():
        if time.time() - lock.stat().st_mtime > LEARNING_COOLDOWN:
            lock.unlink(missing_ok=True)
        else:
            return False
    try:
        lock.write_text(str(os.getpid()), encoding="utf-8")
        return True
    except Exception:
        return False


def release_learn_lock(game_name: str) -> None:
    folder, _, _ = get_game_model_paths(game_name)
    (folder / ".learn.lock").unlink(missing_ok=True)

# =============================================================================
# SCORING
# =============================================================================
def prior_from_all_games(all_data: Dict[str, pd.DataFrame]) -> Dict[int, float]:
    all_draws: List[List[int]] = []
    for df in all_data.values():
        all_draws.extend(draws_from_df(df))
    if not all_draws:
        return {n: 1.0 / 90 for n in range(1, 91)}
    counts = Counter(n for d in all_draws for n in d)
    total = len(all_draws) * 5
    prior = {n: (counts.get(n, 0) + 2) / (total + 180) for n in range(1, 91)}
    s = sum(prior.values()) or 1.0
    return {n: prior[n] / s for n in prior}


def momentum_score(draws: List[List[int]], recent_k: int, prior_k: int) -> Dict[int, float]:
    if len(draws) < 10:
        return {n: 0.0 for n in range(1, 91)}
    recent = draws[-recent_k:] if len(draws) > recent_k else draws
    prior = draws[-(recent_k + prior_k):-recent_k] if len(draws) > recent_k + 5 else []
    rc = Counter(n for d in recent for n in d)
    pc = Counter(n for d in prior for n in d) if prior else Counter()
    raw = {}
    for n in range(1, 91):
        r = rc.get(n, 0) / max(1, len(recent))
        p = pc.get(n, 0) / max(1, len(prior)) if prior else 0.0
        raw[n] = max(0.0, r - p)
    m = max(raw.values()) or 1.0
    return {n: raw[n] / m for n in raw}


def positional_score(draws: List[List[int]]) -> Dict[int, float]:
    if len(draws) < 12:
        return {n: 0.0 for n in range(1, 91)}
    pos = [Counter() for _ in range(5)]
    for d in draws:
        for i, n in enumerate(d):
            pos[i][n] += 1
    total = len(draws)
    out = {}
    for n in range(1, 91):
        ratios = [pos[i].get(n, 0) / max(1.0, total / 90) for i in range(5)]
        out[n] = max(ratios)
    m = max(out.values()) or 1.0
    return {n: out[n] / m for n in out}


def micro_recency_score(draws: List[List[int]], window: int) -> Dict[int, float]:
    recent = draws[-window:] if len(draws) > window else draws
    present = set(n for d in recent for n in d)
    return {n: (1.0 if n in present else 0.0) for n in range(1, 91)}


def overdue_score(draws: List[List[int]], min_gap: int, max_gap: int) -> Dict[int, float]:
    last_seen = {n: None for n in range(1, 91)}
    for i, d in enumerate(draws):
        for n in d:
            last_seen[n] = i
    L = len(draws) - 1
    denom = max(1, max_gap - min_gap)
    scores = {}
    for n in range(1, 91):
        ls = last_seen[n]
        gap = (L - ls) if ls is not None else max_gap
        if gap < min_gap:
            s = 0.0
        elif gap >= max_gap:
            s = 1.0
        else:
            s = (gap - min_gap) / denom
        scores[n] = s
    m = max(scores.values()) or 1.0
    return {n: scores[n] / m for n in scores}


def follow1_score(draws: List[List[int]]) -> Dict[int, float]:
    if len(draws) < 2:
        return {n: 0.0 for n in range(1, 91)}
    one = defaultdict(Counter)
    for i in range(1, len(draws)):
        for x in draws[i - 1]:
            for y in draws[i]:
                one[x][y] += 1
    last = set(draws[-1])
    agg = Counter()
    for x in last:
        agg.update(one.get(x, Counter()))
    if not agg:
        return {n: 0.0 for n in range(1, 91)}
    m = max(agg.values()) or 1.0
    return {n: agg.get(n, 0) / m for n in range(1, 91)}


def combined_score(draws: List[List[int]], prior: Dict[int, float], blend: Dict[str, float], hp: Dict[str, int]) -> Dict[int, float]:
    mom = momentum_score(draws, hp["momentum_recent"], hp["momentum_prior"])
    pos = positional_score(draws)
    mic = micro_recency_score(draws, hp["recency_window"])
    ovd = overdue_score(draws, hp["overdue_min"], hp["overdue_max"])
    fol = follow1_score(draws)
    score = {}
    for n in range(1, 91):
        score[n] = (
            blend["prior"] * prior.get(n, 0.0) +
            blend["momentum"] * mom.get(n, 0.0) +
            blend["position"] * pos.get(n, 0.0) +
            blend["micro_recency"] * mic.get(n, 0.0) +
            blend["overdue"] * ovd.get(n, 0.0) +
            blend["follow1"] * fol.get(n, 0.0)
        )
    mx = max(score.values()) or 1.0
    return {n: score[n] / mx for n in score}


def build_top_sets(draws: List[List[int]], score: Dict[int, float]) -> Dict[str, Any]:
    ranked = [n for n, _ in sorted(score.items(), key=lambda x: x[1], reverse=True)]
    top60, top30, top20, top10 = ranked[:60], ranked[:30], ranked[:20], ranked[:10]
    top5, top2 = top10[:5], top10[:2]
    last = set(draws[-1]) if draws else set()
    banker = max(top5, key=lambda n: (1 if n in last else 0, score.get(n, 0.0))) if top5 else None
    return {"top60": top60, "top30": top30, "top20": top20, "top10": top10, "top5": top5, "top2": top2, "banker": banker}


def predict_one_game(game_name: str, df: pd.DataFrame, all_data: Dict[str, pd.DataFrame], blend: Dict[str, float], hp: Dict[str, int]) -> Optional[Dict[str, Any]]:
    draws = draws_from_df(df)
    if len(draws) < MIN_DRAWS_REQ:
        logger.warning("Insufficient draws for %s: %d < %d", game_name, len(draws), MIN_DRAWS_REQ)
        return None
    prior = prior_from_all_games(all_data)
    score = combined_score(draws, prior, blend, hp)
    preds = build_top_sets(draws, score)
    preds.update({
        "game": game_name,
        "machine": next((g["machine"] for g in GAMES.values() if g["name"] == game_name), "unknown"),
        "total_draws": len(draws),
    })
    return preds

# =============================================================================
# LEARNING / BACKTEST
# =============================================================================
def evaluate_model(game_name: str, df: pd.DataFrame, blend: Dict[str, float], hp: Dict[str, int]) -> Dict[str, float]:
    draws = draws_from_df(df)
    if len(draws) < MIN_DRAWS_REQ + 5:
        return {"top2_hit_rate": 0.0, "banker_hit_rate": 0.0, "validation_score": 0.0}
    start_idx = max(MIN_DRAWS_REQ, len(draws) - 100)
    top2_hits = banker_hits = total = 0
    for i in range(start_idx, len(draws)):
        hist = draws[:i]
        actual = set(draws[i])
        prior = prior_from_all_games({game_name: pd.DataFrame(hist)})
        score = combined_score(hist, prior, blend, hp)
        ranked = [n for n, _ in sorted(score.items(), key=lambda x: x[1], reverse=True)]
        top2 = ranked[:2]
        banker = ranked[0] if ranked else None
        if len(top2) == 2 and top2[0] in actual and top2[1] in actual:
            top2_hits += 1
        if banker in actual:
            banker_hits += 1
        total += 1
    top2_rate = top2_hits / total if total else 0.0
    banker_rate = banker_hits / total if total else 0.0
    return {"top2_hit_rate": top2_rate, "banker_hit_rate": banker_rate, "validation_score": 0.7 * top2_rate + 0.3 * banker_rate}


def learn_game(game_name: str, df: pd.DataFrame, all_data: Dict[str, pd.DataFrame], force: bool = False) -> bool:
    if len(df) < MIN_DRAWS_REQ:
        return False
    active = load_active_model(game_name)
    checksum = compute_checksum(df)
    if not force:
        if time.time() - active.get("last_learn", 0) < LEARNING_COOLDOWN:
            return False
        if active.get("data_checksum") == checksum:
            return False
    if not acquire_learn_lock(game_name):
        return False
    try:
        blend = active.get("blend", BASE_BLEND.copy())
        combos = list(product(MOMENTUM_RECENT_GRID, MOMENTUM_PRIOR_GRID, OVERDUE_MIN_GRID, OVERDUE_MAX_GRID, RECENCY_WINDOW_GRID, PAIR_WINDOW_GRID))
        combos = [c for c in combos if c[2] < c[3]]
        random.shuffle(combos)
        combos = combos[:min(RANDOM_SEARCH_SAMPLES, len(combos))]
        best_score = -1.0
        best_hp = active.get("hyperparams", DEFAULT_HYPERPARAMS.copy())
        for mr, mp, omin, omax, rw, pw in combos:
            hp = {"momentum_recent": mr, "momentum_prior": mp, "overdue_min": omin, "overdue_max": omax, "recency_window": rw, "pair_window": pw}
            perf = evaluate_model(game_name, df, blend, hp)
            if perf["validation_score"] > best_score:
                best_score, best_hp = perf["validation_score"], hp
        candidate = {
            "engine": "Desmond", "game": game_name, "model_id": utc_now().strftime("%Y%m%d_%H%M%S"),
            "created": utc_now().isoformat(), "blend": blend, "hyperparams": best_hp,
            "data_checksum": checksum, "data_rows": len(df), "validation_score": best_score, "last_learn": time.time(),
        }
        path = save_candidate_model(game_name, candidate)
        active_score = active.get("validation_score", 0.0)
        if active_score == 0.0 or ((best_score - active_score) / max(active_score, 1e-9)) >= PROMOTION_THRESHOLD:
            promote_to_active(game_name, path)
        return True
    finally:
        release_learn_lock(game_name)


def backtest_game(game_name: str, df: pd.DataFrame, all_data: Dict[str, pd.DataFrame], last: Optional[int] = None, learn: bool = False) -> Dict[str, Any]:
    if learn:
        learn_game(game_name, df, all_data, force=True)
    draws = draws_from_df(df)
    if len(draws) < MIN_DRAWS_REQ + 1:
        return {"summary": {"game": game_name, "samples": 0}, "rows": []}
    model = load_active_model(game_name)
    blend = model.get("blend", BASE_BLEND.copy())
    hp = model.get("hyperparams", DEFAULT_HYPERPARAMS.copy())
    start = MIN_DRAWS_REQ
    if last is not None:
        start = max(len(draws) - last, start)
    rows = []
    for t in range(start, len(draws)):
        hist = draws[:t]
        target = draws[t]
        score = combined_score(hist, prior_from_all_games({game_name: pd.DataFrame(hist)}), blend, hp)
        ranked = [n for n, _ in sorted(score.items(), key=lambda x: x[1], reverse=True)]
        top30, top10, top5 = ranked[:30], ranked[:10], ranked[:5]
        banker = top5[0] if top5 else None
        rows.append({
            "t": t,
            "top5_hits": len(set(top5) & set(target)),
            "top10_hits": len(set(top10) & set(target)),
            "top30_hits": len(set(top30) & set(target)),
            "banker_hit": 1 if banker in target else 0,
            "pred_top5": "-".join(f"{n:02d}" for n in top5),
            "pred_banker": f"{banker:02d}" if banker else "",
            "actual": "-".join(f"{n:02d}" for n in target),
        })
    samples = len(rows)
    summary = {
        "game": game_name, "samples": samples,
        "top5_avg_hits": round(sum(r["top5_hits"] for r in rows) / samples, 3) if samples else 0,
        "top10_avg_hits": round(sum(r["top10_hits"] for r in rows) / samples, 3) if samples else 0,
        "top30_avg_hits": round(sum(r["top30_hits"] for r in rows) / samples, 3) if samples else 0,
        "banker_hit_rate": round(sum(r["banker_hit"] for r in rows) / samples, 3) if samples else 0,
    }
    return {"summary": summary, "rows": rows}

# =============================================================================
# OUTPUT
# =============================================================================
def fmt(nums: List[int]) -> str:
    return " ".join(f"{int(n):02d}" for n in nums) if nums else "None"


def add_positions(nums: List[int]) -> List[Dict[str, int]]:
    return [{"number": int(n), "position": i + 1} for i, n in enumerate(nums or [])]


def run_context_metadata() -> Dict[str, Any]:
    return {
        "run_mode": os.environ.get("TOC_RUN_MODE", "live"),
        "target_draw_date": os.environ.get("TOC_TARGET_DRAW_DATE") or None,
        "data_cutoff_date": os.environ.get("TOC_DATA_CUTOFF_DATE") or None,
        "late_run": os.environ.get("TOC_RUN_MODE") == "backdated",
        "run_context_id": os.environ.get("TOC_RUN_CONTEXT_ID") or None,
    }


def save_pred_docx(game_name: str, preds: Dict[str, Any]) -> Optional[str]:
    if not DOCX_AVAILABLE:
        return None
    path = SUMMARIES / f"DESMOND_{safe_name(game_name)}_{utc_now().strftime('%Y%m%d_%H%M%S')}.docx"
    doc = Document()
    doc.add_heading(f"DESMOND ENGINE — {game_name}", 0)
    doc.add_paragraph(f"Generated: {utc_now().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    doc.add_paragraph(f"Machine: {preds.get('machine', 'unknown').upper()} | Draws analyzed: {preds.get('total_draws', 0)}")
    for title, key in [("Top 60", "top60"), ("Top 30", "top30"), ("Top 20", "top20"), ("Top 10", "top10"), ("Top 5", "top5"), ("Top 2", "top2")]:
        doc.add_heading(title, 1)
        doc.add_paragraph(fmt(preds.get(key, [])))
    doc.add_heading("Banker", 2)
    doc.add_paragraph(f"{int(preds['banker']):02d}" if preds.get("banker") is not None else "None")
    doc.add_heading("Confidence", 2)
    doc.add_paragraph(f"{float(preds.get('confidence', 0.0)):.6f}")
    doc.save(str(path))
    logger.info("Saved local DOCX: %s", path)
    return str(path)


def get_game_id(game_name: str) -> Optional[int]:
    for gid, info in GAMES.items():
        if info["name"].lower() == game_name.lower():
            return gid
    return None


def save_pred_json(game_name: str, preds: Dict[str, Any]) -> Optional[str]:
    model = load_active_model(game_name)
    path = CONSENSUS_OUT / f"ENGINE_{ENGINE_ID}_{safe_name(game_name)}_{utc_now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}.json"
    payload = {
        "engine": ENGINE_NAME, "engine_id": ENGINE_ID, "game": game_name, "game_id": get_game_id(game_name),
        "run_type": "prediction", "date": utc_now().strftime("%Y-%m-%d"), "generated": utc_now().isoformat(),
        "model_id": model.get("model_id", "unknown"), "data_checksum": model.get("data_checksum"),
        "top60": add_positions(preds.get("top60", [])), "top30": add_positions(preds.get("top30", [])),
        "top20": add_positions(preds.get("top20", [])), "top10": add_positions(preds.get("top10", [])),
        "top5": add_positions(preds.get("top5", [])), "top2": add_positions(preds.get("top2", [])),
        "banker": preds.get("banker"),
        "confidence": float(preds.get("confidence", model.get("validation_score", 0.0)) or 0.0),
        "run_context": run_context_metadata(),
        "meta": {"top60_size": len(preds.get("top60", [])), "top10_size": len(preds.get("top10", []))},
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    logger.info("Consensus JSON saved: %s", path)
    return str(path)


def save_bt_docx(game_name: str, rows: List[Dict], summary: Dict) -> None:
    if not DOCX_AVAILABLE:
        return
    path = BT_DIR / f"DESMOND_BT_{safe_name(game_name)}_{utc_now().strftime('%Y%m%d_%H%M%S')}.docx"
    doc = Document()
    doc.add_heading(f"Backtest — DESMOND ENGINE — {game_name}", 0)
    doc.add_paragraph(f"Samples: {summary.get('samples', 0)}")
    doc.add_paragraph(f"Top5 avg: {summary.get('top5_avg_hits', 0):.3f} | Top10 avg: {summary.get('top10_avg_hits', 0):.3f} | Top30 avg: {summary.get('top30_avg_hits', 0):.3f} | Banker: {summary.get('banker_hit_rate', 0):.3f}")
    for r in rows[-10:]:
        doc.add_paragraph(f"t={r['t']} | top5={r['top5_hits']} top10={r['top10_hits']} top30={r['top30_hits']} banker={r['banker_hit']} | pred5={r['pred_top5']} | actual={r['actual']}")
    doc.save(str(path))

# =============================================================================
# RUNNERS
# =============================================================================
def resolve_game_identifier(val: Optional[str]) -> Optional[str]:
    if val is None:
        return None
    val = str(val).strip()
    if val.isdigit():
        idx = int(val)
        return GAMES[idx]["name"] if idx in GAMES else None
    for info in GAMES.values():
        if info["name"].lower() == val.lower():
            return info["name"]
    return None


def run_prediction_for_game(game_name: str) -> bool:
    all_data = load_all_games()
    df = all_data.get(game_name)
    if df is None or df.empty:
        print("No data for this game.")
        return False
    try:
        learn_game(game_name, df, all_data, force=False)
    except Exception as e:
        logger.error("Auto-learning failed for %s: %s", game_name, e)
    model = load_active_model(game_name)
    preds = predict_one_game(game_name, df, all_data, model.get("blend", BASE_BLEND.copy()), model.get("hyperparams", DEFAULT_HYPERPARAMS.copy()))
    if not preds:
        return False
    preds["confidence"] = float(model.get("validation_score", 0.0) or 0.0)
    save_pred_docx(game_name, preds)
    save_pred_json(game_name, preds)
    print("Top 60:", fmt(preds["top60"]))
    print("Top 30:", fmt(preds["top30"]))
    print("Top 20:", fmt(preds["top20"]))
    print("Top 10:", fmt(preds["top10"]))
    print("Top 5:", fmt(preds["top5"]))
    print("Top 2:", fmt(preds["top2"]))
    print("Banker:", f"{preds['banker']:02d}" if preds.get("banker") else "None")
    print("Confidence:", f"{float(preds.get('confidence', 0.0)):.6f}")
    return True


def run_training_for_game(game_name: str) -> bool:
    all_data = load_all_games()
    df = all_data.get(game_name)
    if df is None or df.empty:
        return False
    return learn_game(game_name, df, all_data, force=True)


def run_backtest(last: Optional[int] = None, only_game: Optional[str] = None, learn: bool = False) -> bool:
    all_data = load_all_games()
    if not all_data:
        return False
    summaries = []
    names = [only_game] if only_game else [GAMES[gid]["name"] for gid in sorted(GAMES.keys())]
    for name in names:
        if not name:
            continue
        df = all_data.get(name)
        if df is None or df.empty:
            continue
        res = backtest_game(name, df, all_data, last=last, learn=learn)
        if res.get("summary", {}).get("samples", 0) > 0:
            summaries.append(res["summary"])
            save_bt_docx(name, res["rows"], res["summary"])
    return bool(summaries)


def run_predict_menu() -> None:
    while True:
        print("\n=== DESMOND ENGINE ===")
        for gid in sorted(GAMES.keys()):
            print(f"{gid:2d}. {GAMES[gid]['name']}")
        print("20. EXIT")
        try:
            s = input("Select game (1-20): ").strip()
        except EOFError:
            return
        if s.isdigit():
            v = int(s)
            if v == 20:
                print("Bye.")
                return
            if v in GAMES:
                ok = run_prediction_for_game(GAMES[v]["name"])
                print("DONE" if ok else "FAILED")


def read_stdin_game_id() -> Optional[int]:
    try:
        line = sys.stdin.readline().strip()
        if line.isdigit() and int(line) in GAMES:
            return int(line)
    except Exception:
        return None
    return None

# =============================================================================
# MAIN: compatible with master launcher
# =============================================================================
def main() -> None:
    ap = argparse.ArgumentParser(description="Desmond Engine V2 — TOC Integrated")
    ap.add_argument("--backtest", action="store_true")
    ap.add_argument("--game", type=str, default=None)
    ap.add_argument("--last", type=int, default=None)
    ap.add_argument("--learn", action="store_true")
    args = ap.parse_args()

    run_type = os.getenv("RUN_TYPE", "prediction").strip().lower()

    if args.backtest or run_type == "backtest":
        game_name = resolve_game_identifier(args.game) if args.game else None
        ok = run_backtest(last=args.last, only_game=game_name, learn=args.learn)
        print("BACKTEST DONE" if ok else "FAILED")
        sys.exit(0 if ok else 1)

    if args.game:
        game_name = resolve_game_identifier(args.game)
        if not game_name:
            print("FAILED")
            sys.exit(1)
    else:
        gid = read_stdin_game_id()
        if gid is None:
            run_predict_menu()
            return
        game_name = GAMES[gid]["name"]

    if run_type == "training":
        ok = run_training_for_game(game_name)
        print("TRAINING COMPLETE" if ok else "FAILED")
        sys.exit(0 if ok else 1)

    ok = run_prediction_for_game(game_name)
    print("DONE" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
