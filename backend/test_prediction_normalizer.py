from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine_data_service import DrawNotFoundError
from prediction_normalizer import (
    PredictionArtifact,
    PredictionDateNormalizer,
    SharedInputStreamAdapter,
    TheresaInputStreamAdapter,
)


@dataclass(frozen=True)
class FixtureDraw:
    draw_date: date

    @property
    def iso_date(self) -> str:
        return self.draw_date.isoformat()


class FixtureDataService:
    def __init__(self, records: dict[str, list[str]]) -> None:
        self._records = {game: tuple(FixtureDraw(date.fromisoformat(value)) for value in dates) for game, dates in records.items()}

    def canonical_game_name(self, game: str) -> str:
        key = " ".join(game.lower().replace("-", " ").split())
        if key not in self._records:
            raise ValueError("unknown game")
        return key

    def records(self, game: str):
        return self._records[game]

    def by_date(self, game: str, target: str):
        target_date = date.fromisoformat(target)
        for record in self._records[game]:
            if record.draw_date == target_date:
                return record
        raise DrawNotFoundError("missing draw")


def artifact(run_date: str, *, game: str = "Friday Bonanza", target: str | None = None, key: str = "fixture") -> PredictionArtifact:
    return PredictionArtifact(
        engine_id="kadija", artifact_path=f"fixtures/{key}.json", artifact_key="prediction", game=game,
        run_timestamp=f"{run_date}T06:30:00+00:00", target_draw_date=target,
        payload_hash=hashlib.sha256(key.encode()).hexdigest(), timestamp_source="generated",
    )


def extended_artifact(
    timestamp: str,
    *,
    engine: str = "kadija",
    target: str | None = None,
    key: str,
    hierarchy: str = "ordinary",
) -> PredictionArtifact:
    return PredictionArtifact(
        engine_id=engine, artifact_path=f"fixtures/{key}.json", artifact_key="prediction",
        game="Friday Bonanza", run_timestamp=timestamp, target_draw_date=target,
        payload_hash=hashlib.sha256(key.encode()).hexdigest(), timestamp_source="generated",
        source_hierarchy=hierarchy,
    )


class PredictionNormalizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.master_fixture = root / "master_data_fixture.json"
        self.master_fixture.write_text(json.dumps({"friday bonanza": ["2026-08-14"], "saturday national": []}), encoding="utf-8")
        self.master_hash = hashlib.sha256(self.master_fixture.read_bytes()).hexdigest()
        records = json.loads(self.master_fixture.read_text(encoding="utf-8"))
        self.normalizer = PredictionDateNormalizer(
            FixtureDataService(records), index_path=root / "index.json", audit_path=root / "audit.jsonl", checkpoint_path=root / "checkpoint.json",
        )

    def write_prediction(
        self,
        path: Path,
        *,
        engine: str,
        generated: str,
        banker: int,
        game: str = "Friday Bonanza",
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "engine": engine,
            "game": game,
            "generated": generated,
            "banker": banker,
            "top5": [banker, 2, 3, 4, 5],
        }), encoding="utf-8")

    def stream_normalizer(self) -> tuple[PredictionDateNormalizer, Path, Path]:
        root = Path(self.temp.name)
        ordinary_root = root / "Consensus_Predictor" / "Fusion_Memory" / "input_streams"
        theresa_root = root / "Banger_Tracker" / "Theresa_Predictor" / "input_stream"
        normalizer = PredictionDateNormalizer(
            FixtureDataService({"friday bonanza": ["2026-08-14"]}),
            index_path=root / "index.json", audit_path=root / "audit.jsonl", checkpoint_path=root / "checkpoint.json",
            adapters=(SharedInputStreamAdapter(ordinary_root), TheresaInputStreamAdapter(theresa_root)),
        )
        return normalizer, ordinary_root, theresa_root

    def tearDown(self) -> None:
        self.temp.cleanup()

    def decision(self, item: PredictionArtifact) -> dict:
        return self.normalizer.preview([item])["decisions"][0]

    def test_same_day_and_one_to_five_day_candidates(self) -> None:
        for delay in range(6):
            item = artifact(f"2026-08-{14 + delay:02d}", key=f"delay-{delay}")
            result = self.decision(item)
            self.assertEqual(result["decision"], "candidate")
            self.assertEqual(result["target_draw_date"], "2026-08-14")
            self.assertEqual(result["delay_days"], delay)
            self.assertEqual(result["late_run"], delay > 0)

    def test_six_and_seven_day_cases_require_review(self) -> None:
        for delay in (6, 7):
            result = self.decision(artifact(f"2026-08-{14 + delay:02d}", key=f"delay-{delay}"))
            self.assertEqual(result["decision"], "manual_review")
            self.assertEqual(result["reason"], "delay_exceeds_automatic_window")

    def test_missing_draw_and_unknown_game_are_not_matched(self) -> None:
        missing = self.decision(artifact("2026-08-15", game="Saturday National", key="missing"))
        unknown = self.decision(artifact("2026-08-15", game="Other Game", key="unknown"))
        self.assertEqual(missing["decision"], "unmatched")
        self.assertEqual(missing["reason"], "no_master_data_draw")
        self.assertEqual(unknown["decision"], "manual_review")

    def test_explicit_target_and_conflict_behavior(self) -> None:
        explicit = self.decision(artifact("2026-08-21", target="2026-08-14", key="explicit"))
        self.assertEqual(explicit["decision"], "already_aligned")
        self.assertEqual(explicit["delay_days"], 7)
        conflict_service = FixtureDataService({"friday bonanza": ["2026-08-14", "2026-08-21"]})
        conflict_normalizer = PredictionDateNormalizer(conflict_service, index_path=Path(self.temp.name) / "conflict-index.json")
        conflict = conflict_normalizer.preview([artifact("2026-08-21", target="2026-08-14", key="conflict")])["decisions"][0]
        self.assertEqual(conflict["decision"], "manual_review")
        self.assertEqual(conflict["reason"], "explicit_target_conflict")

    def test_ambiguity_idempotency_checkpoint_and_master_data_immutability(self) -> None:
        ambiguous_service = FixtureDataService({"friday bonanza": ["2026-08-14", "2026-08-16"]})
        ambiguous = PredictionDateNormalizer(ambiguous_service, index_path=Path(self.temp.name) / "ambiguous-index.json")
        self.assertEqual(ambiguous.preview([artifact("2026-08-17", key="ambiguous")])["decisions"][0]["decision"], "manual_review")
        item = artifact("2026-08-15", key="apply")
        first = self.normalizer.apply([item])
        second = self.normalizer.apply([item])
        self.assertEqual(first["normalized"], 1)
        self.assertEqual(second["normalized"], 0)
        self.assertEqual(second["already_processed"], 1)
        self.assertTrue((Path(self.temp.name) / "checkpoint.json").is_file())
        self.assertEqual(
            self.normalizer.matching_identity(item),
            ("friday bonanza", "2026-08-14"),
        )
        self.assertEqual(hashlib.sha256(self.master_fixture.read_bytes()).hexdigest(), self.master_hash)

    def test_dynamic_multi_engine_discovery_and_theresa_separation(self) -> None:
        normalizer, ordinary_root, theresa_root = self.stream_normalizer()
        for engine in (
            "kadija", "Desmond_Engine", "angel", "henry", "king",
            "lady", "lukas", "ohemaa", "penoukou", "future_engine",
        ):
            self.write_prediction(
                ordinary_root / engine / "prediction.json",
                engine=engine, generated="2026-08-15T10:00:00+00:00", banker=11,
            )
        self.write_prediction(
            ordinary_root / "theresa" / "independent-copy.json",
            engine="theresa", generated="2026-08-15T10:00:00+00:00", banker=11,
        )
        self.write_prediction(
            theresa_root / "Theresa_friday_bonanza_20260815_100000.json",
            engine="theresa", generated="2026-08-15T10:00:00+00:00", banker=12,
        )
        preview = normalizer.preview()
        self.assertEqual(preview["ordinary_engine_folders_discovered"], 10)
        self.assertIn("future_engine", preview["ordinary_engine_ids"])
        self.assertEqual(preview["ordinary"]["artifacts_scanned"], 10)
        self.assertEqual(preview["theresa"]["artifacts_scanned"], 1)
        self.assertEqual(preview["canonical_predictions"], 11)

    def test_latest_different_payload_run_supersedes_and_archives(self) -> None:
        normalizer, ordinary_root, _ = self.stream_normalizer()
        older = ordinary_root / "outside_toc" / "old.json"
        newer = ordinary_root / "outside_toc" / "new.json"
        self.write_prediction(older, engine="outside_toc", generated="2026-08-15T08:00:00+00:00", banker=10)
        self.write_prediction(newer, engine="outside_toc", generated="2026-08-15T12:00:00+00:00", banker=20)
        original_old_content = older.read_bytes()
        preview = normalizer.preview()
        superseded = [item for item in preview["decisions"] if item.get("slot_status") == "superseded"]
        canonical = [item for item in preview["decisions"] if item.get("slot_status") == "canonical"]
        self.assertEqual(len(superseded), 1)
        self.assertEqual(len(canonical), 1)
        self.assertEqual(canonical[0]["artifact_path"], str(newer.resolve()))
        applied = normalizer.apply()
        self.assertFalse(older.exists())
        archived = Path(applied["archive_actions"][0]["archive_path"])
        self.assertTrue(archived.is_relative_to(Path(self.temp.name)))
        self.assertEqual(archived.read_bytes(), original_old_content)
        self.assertNotIn(str(archived), [item.artifact_path for item in normalizer.discover()])
        second = normalizer.apply()
        self.assertEqual(second["archive_actions"], [])

    def test_true_duplicate_and_ambiguous_timestamp_remain_safe(self) -> None:
        normalizer, ordinary_root, _ = self.stream_normalizer()
        duplicate_a = ordinary_root / "kadija" / "copy-a.json"
        duplicate_b = ordinary_root / "kadija" / "copy-b.json"
        self.write_prediction(duplicate_a, engine="kadija", generated="2026-08-15T10:00:00+00:00", banker=10)
        duplicate_b.parent.mkdir(parents=True, exist_ok=True)
        duplicate_b.write_bytes(duplicate_a.read_bytes())
        preview = normalizer.preview()
        self.assertEqual(preview["true_duplicate_copies"], 1)
        self.assertEqual(preview["superseded_runs_proposed"], 0)
        normalizer.apply()
        self.assertEqual(len(normalizer.discover()), 1)
        ambiguous_normalizer, ambiguous_root, _ = self.stream_normalizer()
        self.write_prediction(ambiguous_root / "angel" / "one.json", engine="angel", generated="2026-08-15T10:00:00+00:00", banker=10)
        self.write_prediction(ambiguous_root / "angel" / "two.json", engine="angel", generated="2026-08-15T10:00:00+00:00", banker=20)
        ambiguous = ambiguous_normalizer.preview()
        self.assertEqual(ambiguous["manual_review"], 2)
        self.assertEqual(ambiguous["superseded_runs_proposed"], 0)

    def test_new_later_run_replaces_previous_canonical(self) -> None:
        normalizer, ordinary_root, _ = self.stream_normalizer()
        first = ordinary_root / "kadija" / "first.json"
        self.write_prediction(first, engine="kadija", generated="2026-08-15T10:00:00+00:00", banker=10)
        normalizer.apply()
        second = ordinary_root / "kadija" / "later.json"
        self.write_prediction(second, engine="kadija", generated="2026-08-15T14:00:00+00:00", banker=20)
        preview = normalizer.preview()
        selected = [item for item in preview["decisions"] if item.get("slot_status") == "canonical"]
        self.assertEqual(selected[0]["artifact_path"], str(second.resolve()))
        normalizer.apply()
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())
        self.assertEqual(hashlib.sha256(self.master_fixture.read_bytes()).hexdigest(), self.master_hash)

    def test_explicit_target_and_same_engine_sequence_resolve_extended_reviews(self) -> None:
        service = FixtureDataService({"friday bonanza": ["2026-07-31", "2026-08-07", "2026-08-14"]})
        normalizer = PredictionDateNormalizer(service, index_path=Path(self.temp.name) / "sequence-index.json")
        explicit = extended_artifact("2026-08-21T10:00:00+00:00", target="2026-08-14", key="explicit")
        before = extended_artifact("2026-08-01T10:00:00+00:00", target="2026-07-31", key="before")
        unresolved = extended_artifact("2026-08-13T10:00:00+00:00", key="middle")
        after = extended_artifact("2026-08-15T10:00:00+00:00", target="2026-08-14", key="after")
        preview = normalizer.preview([explicit, before, unresolved, after])
        middle = next(item for item in preview["decisions"] if item["artifact_id"] == unresolved.artifact_id)
        self.assertEqual(next(item for item in preview["decisions"] if item["artifact_id"] == explicit.artifact_id)["decision"], "already_aligned")
        self.assertEqual(middle["decision"], "candidate")
        self.assertEqual(middle["target_draw_date"], "2026-08-07")
        self.assertEqual(middle["reason"], "resolved_by_same_engine_sequence")
        self.assertEqual(preview["original_manual_review"], 1)
        self.assertEqual(preview["resolved_by_extended_evidence"], 1)

    def test_sequence_ambiguity_and_repeated_runs_remain_safe(self) -> None:
        service = FixtureDataService({"friday bonanza": ["2026-07-31", "2026-08-07", "2026-08-14", "2026-08-21"]})
        normalizer = PredictionDateNormalizer(service, index_path=Path(self.temp.name) / "ambiguous-sequence-index.json")
        before = extended_artifact("2026-08-01T10:00:00+00:00", target="2026-07-31", key="before")
        unresolved_one = extended_artifact("2026-08-20T08:00:00+00:00", key="repeat-one")
        unresolved_two = extended_artifact("2026-08-20T12:00:00+00:00", key="repeat-two")
        after = extended_artifact("2026-08-22T10:00:00+00:00", target="2026-08-21", key="after")
        preview = normalizer.preview([before, unresolved_one, unresolved_two, after])
        unresolved = [item for item in preview["decisions"] if item["artifact_id"] in {unresolved_one.artifact_id, unresolved_two.artifact_id}]
        self.assertTrue(all(item["decision"] == "manual_review" for item in unresolved))
        self.assertTrue(all(item["reason"] == "delay_exceeds_automatic_window" for item in unresolved))

    def test_cross_engine_corroboration_requires_two_independent_anchors(self) -> None:
        service = FixtureDataService({"friday bonanza": ["2026-08-14"]})
        normalizer = PredictionDateNormalizer(service, index_path=Path(self.temp.name) / "cross-index.json")
        unresolved = extended_artifact("2026-08-20T10:00:00+00:00", key="target")
        angel = extended_artifact("2026-08-20T09:00:00+00:00", engine="angel", target="2026-08-14", key="angel")
        desmond = extended_artifact("2026-08-20T11:00:00+00:00", engine="desmond", target="2026-08-14", key="desmond")
        resolved = normalizer.preview([unresolved, angel, desmond])
        target = next(item for item in resolved["decisions"] if item["artifact_id"] == unresolved.artifact_id)
        self.assertEqual(target["reason"], "resolved_by_cross_engine_corroboration")
        insufficient = normalizer.preview([unresolved, angel])
        target = next(item for item in insufficient["decisions"] if item["artifact_id"] == unresolved.artifact_id)
        self.assertEqual(target["decision"], "manual_review")
        theresa = extended_artifact("2026-08-20T10:00:00+00:00", engine="theresa", key="theresa-cross", hierarchy="theresa")
        theresa_preview = normalizer.preview([theresa, angel, desmond])
        target = next(item for item in theresa_preview["decisions"] if item["artifact_id"] == theresa.artifact_id)
        self.assertEqual(target["decision"], "manual_review")

    def test_multiple_candidates_reduce_only_when_sequence_is_unique_and_numbers_do_not_matter(self) -> None:
        service = FixtureDataService({"friday bonanza": ["2026-08-14", "2026-08-16", "2026-08-21"]})
        normalizer = PredictionDateNormalizer(service, index_path=Path(self.temp.name) / "multiple-index.json")
        before = extended_artifact("2026-08-14T10:00:00+00:00", target="2026-08-14", key="before")
        middle_a = extended_artifact("2026-08-17T10:00:00+00:00", key="middle-a")
        middle_b = extended_artifact("2026-08-17T10:00:00+00:00", key="middle-b")
        after = extended_artifact("2026-08-22T10:00:00+00:00", target="2026-08-21", key="after")
        preview = normalizer.preview([before, middle_a, after])
        preview_with_different_payload_identity = normalizer.preview([before, middle_b, after])
        first = next(item for item in preview["decisions"] if item["artifact_id"] == middle_a.artifact_id)
        second = next(item for item in preview_with_different_payload_identity["decisions"] if item["artifact_id"] == middle_b.artifact_id)
        self.assertEqual(first["target_draw_date"], "2026-08-16")
        self.assertEqual(second["target_draw_date"], "2026-08-16")

    def test_theresa_sequence_is_separate_and_preview_is_read_only(self) -> None:
        root = Path(self.temp.name)
        service = FixtureDataService({"friday bonanza": ["2026-07-31", "2026-08-07", "2026-08-14"]})
        normalizer = PredictionDateNormalizer(service, index_path=root / "theresa-index.json", audit_path=root / "theresa-audit.jsonl", checkpoint_path=root / "theresa-checkpoint.json")
        before = extended_artifact("2026-08-01T10:00:00+00:00", engine="theresa", target="2026-07-31", key="theresa-before", hierarchy="theresa")
        middle = extended_artifact("2026-08-13T10:00:00+00:00", engine="theresa", key="theresa-middle", hierarchy="theresa")
        after = extended_artifact("2026-08-15T10:00:00+00:00", engine="theresa", target="2026-08-14", key="theresa-after", hierarchy="theresa")
        master_before = self.master_fixture.read_bytes()
        preview = normalizer.preview([before, middle, after])
        resolved = next(item for item in preview["decisions"] if item["artifact_id"] == middle.artifact_id)
        self.assertEqual(resolved["reason"], "resolved_by_same_engine_sequence")
        self.assertEqual(preview["theresa"]["artifacts_scanned"], 3)
        self.assertFalse((root / "theresa-index.json").exists())
        self.assertFalse((root / "theresa-checkpoint.json").exists())
        self.assertEqual(self.master_fixture.read_bytes(), master_before)


if __name__ == "__main__":
    unittest.main()