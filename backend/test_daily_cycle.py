from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
import sys
import runpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from daily_cycle import DailyCycleService, RunContext
from engine_data_service import CutoffDataService


class Draw:
    def __init__(self, game: str, value: str) -> None:
        self.game, self.draw_date, self.iso_date = game, date.fromisoformat(value), value
        self.draw_numbers = (1, 2, 3, 4, 5)


class SharedFixtureService:
    def __init__(self) -> None:
        self._records = {
            "friday bonanza": tuple(Draw("friday bonanza", value) for value in ("2026-08-10", "2026-08-14", "2026-08-15")),
            "monday special": tuple(Draw("monday special", value) for value in ("2026-08-11", "2026-08-16")),
        }
    def records(self, game: str): return self._records[self.canonical_game_name(game)]
    def games(self): return tuple(self._records)
    def canonical_game_name(self, game: str): return " ".join(game.casefold().split())
    def dataset_info(self): return {"ok": True}
    def dataset_sha256(self): return "fixture"
    def game_info(self, game: str): return game
    def by_date(self, game: str, target: date):
        return next(record for record in self._records[game] if record.draw_date == target)


class DataService:
    def canonical_game_name(self, game: str) -> str:
        if game.casefold() != "friday bonanza":
            raise ValueError("unknown game")
        return "friday bonanza"
    def by_date(self, game: str, target: date) -> None:
        if target.isoformat() != "2026-08-14":
            raise ValueError("missing draw")
    def dataset_info(self): return {"ok": True}
    def visible_range(self, cutoff: str): return {"latest_visible_date": "2026-08-13", "target_and_later_excluded": True}


class DailyCycleTests(unittest.TestCase):
    def service(self, calls: list[tuple[str, RunContext]], failures: set[str] = set(), normalizing: bool = False) -> DailyCycleService:
        def adapter(name: str):
            def run(context: RunContext):
                calls.append((name, context))
                return {"status": "error", "message": name} if name in failures else {"status": "success", "cutoff_enforced": True}
            return run
        return DailyCycleService(data_service=DataService(), normalization_running=lambda: normalizing, prediction_engines=adapter("prediction_engines"), theresa=adapter("theresa"), intelligence=adapter("theresa_intelligence"))

    def test_live_and_backdated_context_propagate_in_order(self):
        calls: list[tuple[str, RunContext]] = []
        live = self.service(calls).run({"game": "Friday Bonanza", "target_draw_date": "2026-08-14", "run_mode": "live"})
        self.assertEqual(live["status"], "success")
        self.assertEqual([name for name, _ in calls], ["prediction_engines", "theresa", "theresa_intelligence"])
        self.assertTrue(all(context == calls[0][1] for _, context in calls))
        self.assertFalse(calls[0][1].late_run)
        calls.clear()
        backdated = self.service(calls).run({"game": "Friday Bonanza", "target_draw_date": "2026-08-14", "run_mode": "backdated"})
        self.assertTrue(backdated["context"]["late_run"])
        self.assertEqual(backdated["context"]["data_cutoff_date"], "2026-08-14")

    def test_failure_stop_duplicate_and_normalizer_lock(self):
        calls: list[tuple[str, RunContext]] = []
        failed = self.service(calls, {"prediction_engines"}).run({"game": "Friday Bonanza", "target_draw_date": "2026-08-14", "run_mode": "live"})
        self.assertEqual(failed["failed_stage"], "prediction_engines")
        self.assertEqual([name for name, _ in calls], ["prediction_engines"])
        with self.assertRaisesRegex(RuntimeError, "normalization"):
            self.service([], normalizing=True).run({"game": "Friday Bonanza", "target_draw_date": "2026-08-14", "run_mode": "live"})
        service = self.service([])
        self.assertTrue(service._lock.acquire(blocking=False))
        with self.assertRaisesRegex(RuntimeError, "already running"):
            service.run({"game": "Friday Bonanza", "target_draw_date": "2026-08-14", "run_mode": "live"})
        service._lock.release()

    def test_exclusive_cutoff_hides_target_future_and_preserves_cross_game_history(self):
        view = CutoffDataService(SharedFixtureService(), "2026-08-14")
        visible = [record.iso_date for game in view.games() for record in view.records(game)]
        self.assertEqual(visible, ["2026-08-10", "2026-08-11"])
        self.assertNotIn("2026-08-14", visible)
        self.assertNotIn("2026-08-15", visible)
        self.assertNotIn("2026-08-16", visible)
        self.assertTrue(view.visible_range()["target_and_later_excluded"])

    def test_backdated_stage_without_cutoff_acknowledgement_stops(self):
        def missing_ack(context: RunContext): return {"status": "success"}
        service = DailyCycleService(data_service=DataService(), normalization_running=lambda: False, prediction_engines=missing_ack, theresa=missing_ack, intelligence=missing_ack)
        result = service.run({"game": "Friday Bonanza", "target_draw_date": "2026-08-14", "run_mode": "backdated"})
        self.assertEqual(result["failed_stage"], "prediction_engines")
        self.assertEqual(result["stages"]["theresa"]["status"], "not_run")

    def test_kadija_desmond_and_theresa_loaders_use_cutoff_view(self):
        view = CutoffDataService(SharedFixtureService(), "2026-08-14")
        root = Path(__file__).resolve().parent
        kadija = runpy.run_path(str(root / "engines" / "kadija" / "kadija_engine_toc.py"))
        desmond = runpy.run_path(str(root / "engines" / "desmond" / "desmond_engine_toc.py"))
        theresa = runpy.run_path(str(root / "theresa" / "theresa_engine_toc.py"))
        kadija["load_game_df"].__globals__["get_data_service"] = lambda: view
        desmond["load_game_df"].__globals__["get_data_service"] = lambda: view
        theresa["load_all_games"].__globals__["get_data_service"] = lambda: view
        self.assertEqual(len(kadija["load_game_df"]("Friday Bonanza")), 1)
        self.assertEqual(len(desmond["load_game_df"]("Friday Bonanza")), 1)
        histories = theresa["load_all_games"]()
        self.assertEqual([row["date"] for row in histories["friday bonanza"]], ["2026-08-10"])
        self.assertEqual([row["date"] for row in histories["monday special"]], ["2026-08-11"])


if __name__ == "__main__": unittest.main()