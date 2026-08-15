"""Read-only MASTER_DATA prediction-date alignment service.

Adapters expose the future-engine contract: engine ID, game, run timestamp,
optional target date, and stable artifact location. MASTER_DATA and prediction
payload bytes are never modified; Apply may move superseded exports to an
archive outside their active input stream.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol

from engine_data_service import DataServiceError, DrawNotFoundError

NORMALIZER_VERSION = 1
MAX_AUTOMATIC_DELAY_DAYS = 5
BACKEND_DIR = Path(__file__).resolve().parent
DATA_DIR = BACKEND_DIR / "data"
INDEX_PATH = DATA_DIR / "prediction_normalization_index.json"
AUDIT_PATH = DATA_DIR / "prediction_normalization_audit.jsonl"
CHECKPOINT_PATH = DATA_DIR / "prediction_normalization_checkpoint.json"
ORDINARY_INPUT_STREAM_ROOT = (
    Path.home() / "Documents" / "Consensus_Predictor" / "Fusion_Memory" / "input_streams"
)
THERESA_ROOT = Path.home() / "Documents" / "Banger_Tracker" / "Theresa_Predictor"
THERESA_OUTPUT_DIR = THERESA_ROOT / "input_stream"


@dataclass(frozen=True)
class PredictionArtifact:
    engine_id: str
    artifact_path: str
    artifact_key: str
    game: str | None
    run_timestamp: str | None
    target_draw_date: str | None
    payload_hash: str
    timestamp_source: str
    source_hierarchy: str = "ordinary"
    archive_root: str | None = None

    @property
    def artifact_id(self) -> str:
        value = "|".join((self.engine_id, self.artifact_path, self.artifact_key, self.run_timestamp or "", self.payload_hash))
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


class PredictionArtifactAdapter(Protocol):
    """Minimum contract for a normalizer-compatible prediction system."""
    engine_id: str

    def discover(self) -> Iterable[PredictionArtifact]: ...


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _payload_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _parse_timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()


def _timestamp(payload: dict[str, Any], path: Path) -> tuple[str | None, str]:
    for field in ("run_timestamp", "generated_at", "generated", "timestamp", "run_date"):
        parsed = _parse_timestamp(payload.get(field))
        if parsed:
            return parsed, field
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(), "filesystem_mtime"
    except OSError:
        return None, "unavailable"


def _target(payload: dict[str, Any]) -> str | None:
    for field in ("target_draw_date", "target_date"):
        value = payload.get(field)
        if isinstance(value, str):
            try:
                return date.fromisoformat(value).isoformat()
            except ValueError:
                pass
    return None


def _is_prediction_payload(payload: dict[str, Any]) -> bool:
    game = payload.get("game") or payload.get("target_game")
    prediction_fields = {"banker", "top2", "top5", "top10", "top20", "top30", "top60"}
    return isinstance(game, str) and any(field in payload for field in prediction_fields)


class SharedInputStreamAdapter:
    """Dynamically discovers ordinary-engine exports in immediate engine folders."""

    engine_id = "ordinary-input-streams"

    def __init__(self, root: Path = ORDINARY_INPUT_STREAM_ROOT) -> None:
        self.root = root

    def discover(self) -> Iterable[PredictionArtifact]:
        if not self.root.is_dir():
            return ()
        artifacts: list[PredictionArtifact] = []
        for engine_folder in sorted(path for path in self.root.iterdir() if path.is_dir() and path.name.casefold() != "theresa"):
            for path in sorted(engine_folder.glob("*.json")):
                payload = _read_json(path)
                if payload is None or not _is_prediction_payload(payload):
                    continue
                timestamp, source = _timestamp(payload, path)
                engine = payload.get("engine") or payload.get("engine_id") or engine_folder.name
                game = payload.get("game") or payload.get("target_game")
                artifacts.append(PredictionArtifact(
                    engine_id=str(engine).casefold(), artifact_path=str(path.resolve()), artifact_key="prediction",
                    game=game if isinstance(game, str) else None, run_timestamp=timestamp, target_draw_date=_target(payload),
                    payload_hash=_payload_hash(payload), timestamp_source=source, source_hierarchy="ordinary",
                    archive_root=str(self.root.parent / "normalization_archive"),
                ))
        return artifacts


class TheresaInputStreamAdapter:
    """Discovers Tier 1 exports only from Theresa's separate Banger Tracker stream."""

    engine_id = "theresa"

    def __init__(self, root: Path = THERESA_OUTPUT_DIR) -> None:
        self.root = root

    def discover(self) -> Iterable[PredictionArtifact]:
        if not self.root.is_dir():
            return ()
        artifacts: list[PredictionArtifact] = []
        for path in sorted(self.root.glob("Theresa_*.json")):
            payload = _read_json(path)
            if payload is None or not _is_prediction_payload(payload):
                continue
            timestamp, source = _timestamp(payload, path)
            game = payload.get("game") or payload.get("target_game")
            artifacts.append(PredictionArtifact(
                engine_id="theresa", artifact_path=str(path.resolve()), artifact_key="prediction",
                game=game if isinstance(game, str) else None, run_timestamp=timestamp, target_draw_date=_target(payload),
                payload_hash=_payload_hash(payload), timestamp_source=source, source_hierarchy="theresa",
                archive_root=str(self.root.parent / "normalization_archive"),
            ))
        return artifacts


def default_adapters() -> tuple[PredictionArtifactAdapter, ...]:
    return (SharedInputStreamAdapter(), TheresaInputStreamAdapter())


class PredictionDateNormalizer:
    """Calculates decisions and persists only sidecar metadata/index records."""

    def __init__(self, data_service: Any, *, index_path: Path = INDEX_PATH, audit_path: Path = AUDIT_PATH, checkpoint_path: Path = CHECKPOINT_PATH, adapters: Iterable[PredictionArtifactAdapter] | None = None) -> None:
        self.data_service, self.index_path, self.audit_path, self.checkpoint_path = data_service, index_path, audit_path, checkpoint_path
        self.adapters = tuple(adapters) if adapters is not None else default_adapters()
        self._lock = threading.Lock()

    def discover(self) -> list[PredictionArtifact]:
        artifacts: list[PredictionArtifact] = []
        seen: set[str] = set()
        for adapter in self.adapters:
            for artifact in adapter.discover():
                if artifact.artifact_id not in seen:
                    artifacts.append(artifact)
                    seen.add(artifact.artifact_id)
        return artifacts

    def _load_index(self) -> dict[str, Any]:
        payload = _read_json(self.index_path)
        if payload and isinstance(payload.get("artifacts"), dict):
            return payload
        return {"schema": "toc.prediction_normalization_index", "version": NORMALIZER_VERSION, "artifacts": {}}

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, path)

    def _decision(self, artifact: PredictionArtifact, existing: dict[str, Any] | None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "artifact_id": artifact.artifact_id, "engine": artifact.engine_id, "artifact_path": artifact.artifact_path, "artifact_key": artifact.artifact_key,
            "original_run_timestamp": artifact.run_timestamp, "timestamp_source": artifact.timestamp_source, "previous_target_draw_date": artifact.target_draw_date,
            "payload_hash": artifact.payload_hash, "normalizer_version": NORMALIZER_VERSION,
        }
        if (
            existing
            and existing.get("payload_hash") == artifact.payload_hash
            and existing.get("decision") not in {"manual_review", "unmatched"}
        ):
            preserved = {
                key: existing[key]
                for key in ("canonical_game", "target_draw_date", "delay_days", "late_run", "master_data_reference")
                if key in existing
            }
            return {**result, **preserved, "decision": "already_processed", "reason": "unchanged_artifact"}
        if not artifact.game:
            return {**result, "decision": "manual_review", "reason": "missing_game"}
        try:
            game = self.data_service.canonical_game_name(artifact.game)
        except (DataServiceError, ValueError, TypeError):
            return {**result, "decision": "manual_review", "reason": "game_not_recognized"}
        result["canonical_game"] = game
        if not artifact.run_timestamp:
            return {**result, "decision": "manual_review", "reason": "missing_run_timestamp"}
        if artifact.timestamp_source == "filesystem_mtime":
            return {**result, "decision": "manual_review", "reason": "weak_filesystem_timestamp"}
        run_date = datetime.fromisoformat(artifact.run_timestamp).date()
        if artifact.target_draw_date:
            try:
                self.data_service.by_date(game, artifact.target_draw_date)
            except DrawNotFoundError:
                return {**result, "decision": "unmatched", "reason": "explicit_target_missing_master_data"}
            delay = (run_date - date.fromisoformat(artifact.target_draw_date)).days
            if delay < 0:
                return {**result, "decision": "manual_review", "reason": "explicit_target_after_run"}
            current_candidates = [record for record in self.data_service.records(game) if 0 <= (run_date - record.draw_date).days <= MAX_AUTOMATIC_DELAY_DAYS]
            if current_candidates and all(record.iso_date != artifact.target_draw_date for record in current_candidates):
                return {**result, "decision": "manual_review", "reason": "explicit_target_conflict", "target_draw_date": artifact.target_draw_date, "delay_days": delay}
            return {**result, "decision": "already_aligned", "reason": "explicit_valid_target", "target_draw_date": artifact.target_draw_date, "delay_days": delay, "late_run": delay > 0, "master_data_reference": f"{game}|{artifact.target_draw_date}"}
        candidates = [record for record in self.data_service.records(game) if 0 <= (run_date - record.draw_date).days <= MAX_AUTOMATIC_DELAY_DAYS]
        if len(candidates) == 1:
            target = candidates[0].iso_date
            delay = (run_date - candidates[0].draw_date).days
            return {**result, "decision": "candidate", "reason": "master_data_alignment", "target_draw_date": target, "delay_days": delay, "late_run": delay > 0, "master_data_reference": f"{game}|{target}"}
        if len(candidates) > 1:
            return {**result, "decision": "manual_review", "reason": "multiple_master_data_candidates"}
        older = [record for record in self.data_service.records(game) if record.draw_date <= run_date]
        if not older:
            return {**result, "decision": "unmatched", "reason": "no_master_data_draw"}
        return {**result, "decision": "manual_review", "reason": "delay_exceeds_automatic_window", "delay_days": (run_date - older[-1].draw_date).days}

    @staticmethod
    def _count(items: Iterable[dict[str, Any]], key: str, value: str) -> int:
        return sum(item.get(key) == value for item in items)

    @staticmethod
    def _reliable_timestamp(decision: dict[str, Any]) -> bool:
        return (
            isinstance(decision.get("original_run_timestamp"), str)
            and decision.get("timestamp_source") not in {"filesystem_mtime", "unavailable"}
        )

    @staticmethod
    def _run_time(decision: dict[str, Any]) -> datetime:
        return datetime.fromisoformat(str(decision["original_run_timestamp"]))

    def _resolved_anchor(self, decision: dict[str, Any]) -> bool:
        return (
            decision.get("decision") in {"candidate", "already_aligned", "already_processed"}
            and isinstance(decision.get("target_draw_date"), str)
            and self._reliable_timestamp(decision)
        )

    def _resolve_by_same_engine_sequence(
        self,
        decision: dict[str, Any],
        anchors: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not self._reliable_timestamp(decision):
            return None
        run_time = self._run_time(decision)
        prior = [anchor for anchor in anchors if self._run_time(anchor) < run_time]
        following = [anchor for anchor in anchors if self._run_time(anchor) > run_time]
        if not prior or not following:
            return None
        before, after = max(prior, key=self._run_time), min(following, key=self._run_time)
        before_date = date.fromisoformat(str(before["target_draw_date"]))
        after_date = date.fromisoformat(str(after["target_draw_date"]))
        if before_date >= after_date:
            return None
        between = [
            record for record in self.data_service.records(decision["canonical_game"])
            if before_date < record.draw_date < after_date
        ]
        if len(between) != 1:
            return None
        target = between[0].iso_date
        delay = (run_time.date() - between[0].draw_date).days
        if delay < 0:
            return None
        return {
            **decision,
            "decision": "candidate",
            "reason": "resolved_by_same_engine_sequence",
            "previous_manual_reason": decision["reason"],
            "target_draw_date": target,
            "delay_days": delay,
            "late_run": delay > 0,
            "master_data_reference": f"{decision['canonical_game']}|{target}",
            "resolution_strength": "anchored_sequence",
            "supporting_anchor_ids": [before["artifact_id"], after["artifact_id"]],
        }

    def _resolve_by_cross_engine_corroboration(
        self,
        decision: dict[str, Any],
        anchors: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not self._reliable_timestamp(decision):
            return None
        run_time = self._run_time(decision)
        candidate_anchors: dict[str, list[dict[str, Any]]] = {}
        for anchor in anchors:
            if anchor["engine"] == decision["engine"]:
                continue
            if abs((self._run_time(anchor) - run_time).total_seconds()) > 24 * 60 * 60:
                continue
            candidate_anchors.setdefault(str(anchor["target_draw_date"]), []).append(anchor)
        proven = {
            target: target_anchors
            for target, target_anchors in candidate_anchors.items()
            if len({anchor["engine"] for anchor in target_anchors}) >= 2
        }
        if len(proven) != 1:
            return None
        target, target_anchors = next(iter(proven.items()))
        try:
            target_record = self.data_service.by_date(decision["canonical_game"], target)
        except DrawNotFoundError:
            return None
        delay = (run_time.date() - target_record.draw_date).days
        if delay < 0:
            return None
        return {
            **decision,
            "decision": "candidate",
            "reason": "resolved_by_cross_engine_corroboration",
            "previous_manual_reason": decision["reason"],
            "target_draw_date": target,
            "delay_days": delay,
            "late_run": delay > 0,
            "master_data_reference": f"{decision['canonical_game']}|{target}",
            "resolution_strength": "corroborated_sequence",
            "supporting_anchor_ids": [anchor["artifact_id"] for anchor in target_anchors],
        }

    def _resolve_manual_reviews(self, decisions: list[dict[str, Any]]) -> None:
        """Upgrade only uniquely proven manual records; leave all ambiguity intact."""
        anchors = [decision for decision in decisions if self._resolved_anchor(decision)]
        for decision in decisions:
            if decision.get("decision") != "manual_review":
                continue
            if decision.get("reason") not in {
                "delay_exceeds_automatic_window",
                "multiple_master_data_candidates",
            }:
                continue
            same_engine = [
                anchor for anchor in anchors
                if anchor["engine"] == decision["engine"]
                and anchor.get("canonical_game") == decision.get("canonical_game")
            ]
            resolved = self._resolve_by_same_engine_sequence(decision, same_engine)
            if resolved is None and decision.get("source_hierarchy") != "theresa":
                same_game = [
                    anchor for anchor in anchors
                    if anchor.get("canonical_game") == decision.get("canonical_game")
                ]
                resolved = self._resolve_by_cross_engine_corroboration(decision, same_game)
            if resolved is not None:
                decision.clear()
                decision.update(resolved)
                anchors.append(decision)

    def _plan(self, artifacts: Iterable[PredictionArtifact] | None = None) -> tuple[list[PredictionArtifact], list[dict[str, Any]]]:
        index = self._load_index()["artifacts"]
        discovered = list(artifacts) if artifacts is not None else self.discover()
        decisions = [self._decision(artifact, index.get(artifact.artifact_id)) for artifact in discovered]
        artifact_by_id = {artifact.artifact_id: artifact for artifact in discovered}
        for decision in decisions:
            artifact = artifact_by_id[decision["artifact_id"]]
            decision["source_hierarchy"] = artifact.source_hierarchy
            decision["archive_root"] = artifact.archive_root
        original_manual_review = self._count(decisions, "decision", "manual_review")
        self._resolve_manual_reviews(decisions)
        resolved = [
            decision for decision in decisions
            if decision["decision"] in {"candidate", "already_aligned", "already_processed"}
            and isinstance(decision.get("target_draw_date"), str)
        ]
        slots: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for decision in resolved:
            slot = (decision["engine"], decision["canonical_game"], decision["target_draw_date"])
            slots.setdefault(slot, []).append(decision)
        for slot, runs in slots.items():
            duplicates: dict[tuple[str, str], list[dict[str, Any]]] = {}
            for run in runs:
                duplicates.setdefault((str(run.get("original_run_timestamp")), run["payload_hash"]), []).append(run)
            logical_runs: list[dict[str, Any]] = []
            for copies in duplicates.values():
                copies.sort(key=lambda item: item["artifact_path"])
                logical_runs.append(copies[0])
                for duplicate in copies[1:]:
                    duplicate["slot_status"] = "duplicate"
                    duplicate["canonical_artifact_id"] = copies[0]["artifact_id"]
                    duplicate["supersession_reason"] = "true_duplicate_copy"
            timestamps = [str(run.get("original_run_timestamp") or "") for run in logical_runs]
            if len(set(timestamps)) != len(timestamps):
                for run in logical_runs:
                    run["decision"] = "manual_review"
                    run["reason"] = "ambiguous_reliable_timestamp"
                continue
            logical_runs.sort(key=lambda item: str(item["original_run_timestamp"]))
            canonical = logical_runs[-1]
            canonical["slot_status"] = "canonical"
            canonical["slot_identity"] = "|".join(slot)
            for run in logical_runs[:-1]:
                run["slot_status"] = "superseded"
                run["canonical_artifact_id"] = canonical["artifact_id"]
                run["supersession_reason"] = "newer_run_exists_for_same_engine_game_target"
                run["slot_identity"] = "|".join(slot)
        return discovered, decisions, original_manual_review

    def preview(self, artifacts: Iterable[PredictionArtifact] | None = None) -> dict[str, Any]:
        discovered, decisions, original_manual_review = self._plan(artifacts)
        ordinary_engines = sorted({artifact.engine_id for artifact in discovered if artifact.source_hierarchy == "ordinary"})
        ordinary_decisions = [item for item in decisions if item["source_hierarchy"] == "ordinary"]
        theresa_decisions = [item for item in decisions if item["source_hierarchy"] == "theresa"]
        def summary(items: list[dict[str, Any]]) -> dict[str, int]:
            slots = {item.get("slot_identity") for item in items if item.get("slot_identity")}
            return {
                "artifacts_scanned": len(items), "logical_slots": len(slots),
                "already_aligned": self._count(items, "decision", "already_aligned"),
                "date_corrections_proposed": self._count(items, "decision", "candidate"),
                "canonical_predictions": self._count(items, "slot_status", "canonical"),
                "superseded_proposed": self._count(items, "slot_status", "superseded"),
                "true_duplicates": self._count(items, "slot_status", "duplicate"),
                "manual_review": self._count(items, "decision", "manual_review"),
                "unmatched": self._count(items, "decision", "unmatched"),
            }
        engine_summaries = {
            engine: summary([item for item in ordinary_decisions if item["engine"] == engine])
            for engine in ordinary_engines
        }
        global_summary = summary(decisions)
        return {
            "status": "success", "mode": "preview", "normalizer_version": NORMALIZER_VERSION,
            "maximum_automatic_delay_days": MAX_AUTOMATIC_DELAY_DAYS, "master_data_modified": False,
            "artifacts_scanned": len(decisions), "safe_normalization_candidates": self._count(decisions, "decision", "candidate"),
            "already_aligned": self._count(decisions, "decision", "already_aligned"),
            "already_processed": self._count(decisions, "decision", "already_processed"),
            "unmatched": global_summary["unmatched"], "manual_review": global_summary["manual_review"],
            "original_manual_review": original_manual_review,
            "resolved_by_extended_evidence": original_manual_review - global_summary["manual_review"],
            "resolution_methods": {
                method: self._count(decisions, "reason", method)
                for method in (
                    "resolved_by_same_engine_sequence",
                    "resolved_by_cross_engine_corroboration",
                )
            },
            "ordinary_engine_folders_discovered": len(ordinary_engines), "ordinary_engine_ids": ordinary_engines,
            "ordinary": summary(ordinary_decisions), "theresa": summary(theresa_decisions),
            "logical_prediction_slots": global_summary["logical_slots"],
            "repeated_run_groups": sum(1 for item in decisions if item.get("slot_status") == "superseded"),
            "canonical_predictions": global_summary["canonical_predictions"],
            "superseded_runs_proposed": global_summary["superseded_proposed"],
            "true_duplicate_copies": global_summary["true_duplicates"], "engine_summaries": engine_summaries,
            "decisions": decisions,
        }

    def matching_identity(self, artifact: PredictionArtifact) -> tuple[str, str] | None:
        """Resolve only a validated canonical game/date identity for matching."""
        if not artifact.game:
            return None
        try:
            game = self.data_service.canonical_game_name(artifact.game)
            if artifact.target_draw_date:
                self.data_service.by_date(game, artifact.target_draw_date)
                return game, artifact.target_draw_date
        except (DataServiceError, ValueError, TypeError):
            return None
        record = self._load_index()["artifacts"].get(artifact.artifact_id)
        target = record.get("target_draw_date") if isinstance(record, dict) else None
        if not isinstance(target, str):
            return None
        try:
            self.data_service.by_date(game, target)
        except (DataServiceError, ValueError, TypeError):
            return None
        return game, target

    def apply(self, artifacts: Iterable[PredictionArtifact] | None = None) -> dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("Normalization is already running.")
        try:
            preview, index, now = self.preview(artifacts), self._load_index(), datetime.now(timezone.utc).isoformat()
            stored, changes = index["artifacts"], []
            for decision in preview["decisions"]:
                record = {**decision, "normalized_at": now}
                previous = stored.get(decision["artifact_id"])
                comparable = {key: value for key, value in record.items() if key != "normalized_at"}
                previous_comparable = {key: value for key, value in previous.items() if key != "normalized_at"} if isinstance(previous, dict) else None
                if comparable != previous_comparable:
                    stored[decision["artifact_id"]] = record
                    changes.append(record)
            if changes and not self.checkpoint_path.exists():
                backup_dir = self.index_path.parent / "normalization_backups" / now.replace(":", "-")
                backup_dir.mkdir(parents=True, exist_ok=True)
                existing_state = []
                for state_path in (self.index_path, self.audit_path, self.checkpoint_path):
                    if state_path.is_file():
                        (backup_dir / state_path.name).write_bytes(state_path.read_bytes())
                        existing_state.append(state_path.name)
                (backup_dir / "manifest.json").write_text(json.dumps({
                    "created_at": now,
                    "existing_normalization_state": existing_state,
                    "prediction_artifacts_modified": False,
                    "master_data_modified": False,
                }, indent=2), encoding="utf-8")
            archive_actions: list[dict[str, str]] = []
            for record in changes:
                if record.get("slot_status") not in {"superseded", "duplicate"}:
                    continue
                source = Path(record["artifact_path"])
                archive_root = record.get("archive_root")
                if not archive_root or not source.is_file():
                    continue
                destination = Path(archive_root) / record["engine"] / str(record.get("target_draw_date") or "unresolved") / source.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    if _payload_hash(_read_json(destination) or {}) != record["payload_hash"]:
                        raise RuntimeError(f"Archive destination already exists with different content: {destination}")
                else:
                    shutil.move(str(source), str(destination))
                record["archived_path"] = str(destination)
                record["archived_at"] = now
                archive_actions.append({"artifact_id": record["artifact_id"], "archive_path": str(destination)})
            if changes:
                index["slots"] = {
                    item["slot_identity"]: {
                        "canonical_artifact_id": item["artifact_id"],
                        "canonical_run_timestamp": item["original_run_timestamp"],
                        "resolved_at": now, "normalizer_version": NORMALIZER_VERSION,
                    }
                    for item in preview["decisions"] if item.get("slot_status") == "canonical"
                }
                self._write_json(self.index_path, index)
            if changes:
                self.audit_path.parent.mkdir(parents=True, exist_ok=True)
                with self.audit_path.open("a", encoding="utf-8") as output:
                    output.writelines(json.dumps(record, sort_keys=True) + "\n" for record in changes)
            checkpoint = {"last_completed_at": now, "normalizer_version": NORMALIZER_VERSION, "artifacts_scanned": preview["artifacts_scanned"], "artifacts_normalized": preview["safe_normalization_candidates"], "artifacts_already_aligned": preview["already_aligned"], "artifacts_already_processed": preview["already_processed"], "artifacts_unmatched": preview["unmatched"], "artifacts_manual_review": preview["manual_review"], "archive_actions": len(archive_actions), "master_data_modified": False}
            if changes:
                self._write_json(self.checkpoint_path, checkpoint)
            return {**preview, "mode": "apply", "normalized": preview["safe_normalization_candidates"], "archive_actions": archive_actions, "checkpoint": checkpoint}
        finally:
            self._lock.release()

    def status(self) -> dict[str, Any]:
        return {"status": "success", "service_available": True, "normalizer_version": NORMALIZER_VERSION, "running": self._lock.locked(), "checkpoint": _read_json(self.checkpoint_path), "master_data_modified": False}