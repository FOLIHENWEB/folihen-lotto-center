"""Daily Cycle orchestration only; prediction systems retain all engine logic."""
from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable


@dataclass(frozen=True)
class RunContext:
    game: str
    registry_id: int | None
    target_draw_date: str
    run_date: str
    run_timestamp: str
    run_mode: str
    late_run: bool
    data_cutoff_date: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class DailyCycleService:
    def __init__(
        self,
        *,
        data_service: Any,
        normalization_running: Callable[[], bool],
        prediction_engines: Callable[[RunContext], dict[str, Any]],
        theresa: Callable[[RunContext], dict[str, Any]],
        intelligence: Callable[[RunContext], dict[str, Any]],
    ) -> None:
        self.data_service = data_service
        self.normalization_running = normalization_running
        self.prediction_engines = prediction_engines
        self.theresa = theresa
        self.intelligence = intelligence
        self._lock = threading.Lock()

    def health(self) -> dict[str, Any]:
        try:
            self.data_service.dataset_info()
            return {"status": "ready", "service": "daily_cycle", "running": self._lock.locked()}
        except Exception as exc:
            return {"status": "unavailable", "service": "daily_cycle", "running": self._lock.locked(), "message": str(exc)}

    def build_context(self, payload: dict[str, Any]) -> RunContext:
        game = self.data_service.canonical_game_name(str(payload.get("game") or ""))
        target = date.fromisoformat(str(payload.get("target_draw_date") or ""))
        mode = str(payload.get("run_mode") or "live")
        if mode not in {"live", "backdated"}:
            raise ValueError("run_mode must be live or backdated.")
        now = datetime.now(timezone.utc)
        if mode == "backdated":
            self.data_service.by_date(game, target)
        return RunContext(
            game=game,
            registry_id=None,
            target_draw_date=target.isoformat(),
            run_date=now.date().isoformat(),
            run_timestamp=now.isoformat(),
            run_mode=mode,
            late_run=mode == "backdated",
            data_cutoff_date=(target.isoformat() if mode == "backdated" else None),
        )

    @staticmethod
    def _stage(result: dict[str, Any]) -> dict[str, Any]:
        return {"status": result.get("status", "error"), "message": result.get("message")}

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("Daily Cycle is already running.")
        try:
            if self.normalization_running():
                raise RuntimeError("Cannot run Daily Cycle while normalization is applying.")
            context = self.build_context(payload)
            if context.run_mode == "backdated":
                visible = self.data_service.visible_range(context.data_cutoff_date)
                if not visible["target_and_later_excluded"] or visible["latest_visible_date"] >= context.target_draw_date:
                    raise RuntimeError("Backdated data cutoff could not be enforced safely.")
            stages: dict[str, dict[str, Any]] = {"preflight": {"status": "success"}}
            for name in ("prediction_engines", "theresa", "theresa_intelligence", "refresh"):
                stages[name] = {"status": "not_run"}
            for name, adapter in (("prediction_engines", self.prediction_engines), ("theresa", self.theresa), ("theresa_intelligence", self.intelligence)):
                result = adapter(context)
                stages[name] = self._stage(result)
                if context.run_mode == "backdated" and result.get("cutoff_enforced") is not True:
                    stages[name] = {"status": "error", "message": "Backdated data cutoff could not be enforced safely."}
                    return {"status": "error", "failed_stage": name, "message": "Backdated data cutoff could not be enforced safely.", "context": context.as_dict(), "stages": stages}
                if result.get("status") != "success":
                    return {"status": "error", "failed_stage": name, "message": result.get("message", f"{name} failed."), "context": context.as_dict(), "stages": stages}
            stages["refresh"] = {"status": "success", "message": "Latest persisted outputs are ready for refresh."}
            return {"status": "success", "cycle_id": str(uuid.uuid4()), "context": context.as_dict(), "stages": stages}
        finally:
            self._lock.release()