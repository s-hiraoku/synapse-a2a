from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from synapse.observation import ObservationCollector

logger = logging.getLogger(__name__)


class _StatusObserverHost(Protocol):
    _status_callbacks: list[Callable[[str, str], None]]
    _observation_collector: ObservationCollector | None
    _observation_attached: bool
    agent_id: str | None
    agent_type: str | None
    lock: threading.Lock
    _task_active_count: int
    _task_active_since: float | None

    def record_status_change(
        self, old_status: str, new_status: str, trigger: str
    ) -> None: ...

    def on_status_change(self, callback: Callable[[str, str], None]) -> None: ...

    def attach_observation_collector(
        self, collector: ObservationCollector | None
    ) -> None: ...

    def _ensure_observation_collector(self) -> ObservationCollector | None: ...


class StatusObserverMixin:
    """Status callback and observation helper methods for TerminalController."""

    _status_callbacks: list[Callable[[str, str], None]]
    _observation_collector: ObservationCollector | None
    _observation_attached: bool
    agent_id: str | None
    agent_type: str | None
    lock: threading.Lock
    _task_active_count: int
    _task_active_since: float | None

    def on_status_change(
        self: _StatusObserverHost, callback: Callable[[str, str], None]
    ) -> None:
        """Register a callback invoked on status transitions."""
        self._status_callbacks.append(callback)

    def _dispatch_status_callbacks(
        self: _StatusObserverHost, old_status: str, new_status: str
    ) -> None:
        """Run registered status callbacks without blocking the caller."""
        if not self._status_callbacks:
            return

        callbacks = list(self._status_callbacks)

        def _fire_callbacks() -> None:
            for callback in callbacks:
                try:
                    callback(old_status, new_status)
                except Exception:
                    logger.exception("Status callback error")

        threading.Thread(target=_fire_callbacks, daemon=True).start()

    def attach_observation_collector(
        self: _StatusObserverHost, collector: ObservationCollector | None
    ) -> None:
        """Attach an observation collector and status-change hook."""
        self._observation_collector = collector
        if self._observation_attached or not collector:
            return

        def _record_status(old_status: str, new_status: str) -> None:
            self.record_status_change(old_status, new_status, "status_transition")

        self.on_status_change(_record_status)
        self._observation_attached = True

    def _ensure_observation_collector(
        self: _StatusObserverHost,
    ) -> ObservationCollector | None:
        """Lazily initialize the observation collector from environment."""
        if self._observation_collector is None:
            try:
                from synapse.observation import ObservationCollector

                self.attach_observation_collector(ObservationCollector.from_env())
            except Exception:
                logger.exception("Failed to initialize observation collector")
                return None
        return self._observation_collector

    def record_status_change(
        self: _StatusObserverHost, old_status: str, new_status: str, trigger: str
    ) -> None:
        """Record a controller status transition if observation is enabled."""
        collector = self._ensure_observation_collector()
        if not collector or not self.agent_id:
            return
        collector.record_status_change(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            from_status=old_status,
            to_status=new_status,
            trigger=trigger,
        )

    def record_task_received(
        self: _StatusObserverHost,
        message: str,
        sender: str | None,
        priority: int,
    ) -> None:
        """Record a received task if observation is enabled."""
        collector = self._ensure_observation_collector()
        if not collector or not self.agent_id:
            return
        collector.record_task_received(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            message=message,
            sender=sender,
            priority=priority,
        )

    def record_task_completed(
        self: _StatusObserverHost,
        task_id: str,
        duration: float | None,
        status: str,
        output_summary: str,
    ) -> None:
        """Record a completed task if observation is enabled."""
        collector = self._ensure_observation_collector()
        if not collector or not self.agent_id:
            return
        collector.record_task_completed(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            task_id=task_id,
            duration=duration,
            status=status,
            output_summary=output_summary,
        )

    def record_error(
        self: _StatusObserverHost,
        error_type: str,
        error_message: str,
        recovery_action: str | None = None,
    ) -> None:
        """Record an error if observation is enabled."""
        collector = self._ensure_observation_collector()
        if not collector or not self.agent_id:
            return
        collector.record_error(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            error_type=error_type,
            error_message=error_message,
            recovery_action=recovery_action,
        )

    @staticmethod
    def task_duration_seconds(created_at: str | None) -> float | None:
        """Return elapsed seconds since task creation timestamp."""
        if not created_at:
            return None
        try:
            created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            return None
        return max(
            0.0,
            (
                datetime.now(timezone.utc) - created_dt.astimezone(timezone.utc)
            ).total_seconds(),
        )

    def set_task_active(self: _StatusObserverHost) -> None:
        """Increment task active count (suppresses READY while > 0)."""
        with self.lock:
            self._task_active_count += 1
            self._task_active_since = time.time()

    def clear_task_active(self: _StatusObserverHost) -> None:
        """Decrement task active count (allows READY when reaches 0)."""
        with self.lock:
            self._task_active_count = max(0, self._task_active_count - 1)
            if self._task_active_count == 0:
                self._task_active_since = None
