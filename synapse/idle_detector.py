from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from synapse.config import WAITING_EXPIRY_SECONDS
from synapse.status import DONE_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StatusDecision:
    new_status: str
    clear_done_time: bool = False


@dataclass(frozen=True)
class IdleStateEvaluation:
    pattern_match: bool
    timeout_idle: bool
    is_idle: bool
    is_waiting: bool
    new_status: str
    clear_done_time: bool
    pattern_detected: bool
    waiting_pattern_time: float | None


class IdleDetector:
    def __init__(
        self,
        idle_detection: dict | None = None,
        waiting_detection: dict | None = None,
        *,
        strip_ansi_fn: Callable[[str], str] | None = None,
    ) -> None:
        self.idle_config = idle_detection or {"strategy": "timeout", "timeout": 1.5}
        self.idle_strategy = self.idle_config.get("strategy", "pattern")
        self.idle_regex = self._compile_idle_regex()
        self.output_idle_threshold = self.idle_config.get("timeout", 1.5)

        self.waiting_config = waiting_detection or {}
        self.waiting_regex = self._compile_waiting_regex()
        self.waiting_require_idle = self.waiting_config.get("require_idle", True)
        self.waiting_idle_timeout = float(self.waiting_config.get("idle_timeout", 0.5))
        self.waiting_expiry = float(
            self.waiting_config.get("waiting_expiry", WAITING_EXPIRY_SECONDS)
        )
        self._strip_ansi = strip_ansi_fn or (lambda text: text)

    def _compile_idle_regex(self) -> re.Pattern[bytes] | None:
        if self.idle_strategy not in ("pattern", "hybrid"):
            return None

        pattern = self.idle_config.get("pattern", "")
        try:
            if pattern == "BRACKETED_PASTE_MODE":
                return re.compile(b"\x1b\\[\\?2004h")
            if pattern:
                return re.compile(pattern.encode("utf-8"))
        except re.error as exc:
            logger.error(
                f"Invalid idle detection pattern '{pattern}': {exc}. "
                f"Falling back to timeout-based idle detection."
            )
        except Exception as exc:
            logger.error(
                f"Unexpected error compiling pattern '{pattern}': {exc}. "
                f"Falling back to timeout-based idle detection."
            )
        return None

    def _compile_waiting_regex(self) -> re.Pattern[str] | None:
        waiting_regex_str = self.waiting_config.get("regex")
        if not waiting_regex_str:
            return None
        try:
            return re.compile(waiting_regex_str, re.MULTILINE)
        except re.error as exc:
            logger.error(
                f"Invalid waiting_detection regex '{waiting_regex_str}': {exc}"
            )
            return None

    def check_pattern_idle(self, output_buffer: bytes, pattern_detected: bool) -> bool:
        if self.idle_strategy not in ("pattern", "hybrid") or not self.idle_regex:
            return False

        pattern_use = self.idle_config.get("pattern_use", "always")
        should_check = pattern_use == "always" or (
            pattern_use == "startup_only" and not pattern_detected
        )
        if not should_check:
            return False

        return bool(self.idle_regex.search(output_buffer))

    def check_timeout_idle(
        self,
        *,
        last_output_time: float | None,
        pattern_detected: bool,
    ) -> bool:
        if self.idle_strategy not in ("timeout", "hybrid"):
            return False

        if self.idle_strategy == "hybrid" and not pattern_detected:
            return False

        if not last_output_time:
            return False

        elapsed: float = time.time() - last_output_time
        return bool(elapsed >= self.output_idle_threshold)

    def evaluate_idle_status(self, pattern_match: bool, timeout_idle: bool) -> bool:
        strategy_map = {
            "pattern": pattern_match,
            "timeout": timeout_idle,
            "hybrid": pattern_match or timeout_idle,
        }
        return strategy_map.get(self.idle_strategy, False)

    def determine_new_status(
        self,
        *,
        current_status: str,
        is_idle: bool,
        is_waiting: bool,
        done_time: float | None,
        task_protection_active: bool,
        has_file_locks: bool,
    ) -> StatusDecision:
        if current_status == "SHUTTING_DOWN":
            return StatusDecision("SHUTTING_DOWN")

        if is_waiting:
            base_status = "WAITING"
        elif is_idle:
            base_status = "READY"
        else:
            base_status = "PROCESSING"

        if base_status == "READY" and (task_protection_active or has_file_locks):
            base_status = "PROCESSING"

        if current_status != "DONE":
            return StatusDecision(base_status)

        if not is_idle and not is_waiting:
            return StatusDecision("PROCESSING", clear_done_time=True)

        if is_waiting:
            return StatusDecision("WAITING", clear_done_time=True)

        done_timeout_expired = done_time and (
            time.time() - done_time >= DONE_TIMEOUT_SECONDS
        )
        if done_timeout_expired:
            return StatusDecision("READY", clear_done_time=True)

        return StatusDecision("DONE")

    def check_waiting_state(
        self,
        *,
        new_data: bytes,
        output_buffer: bytes,
        last_output_time: float | None,
        waiting_pattern_time: float | None,
    ) -> tuple[bool, float | None]:
        if not self.waiting_regex:
            return False, waiting_pattern_time

        new_text = (
            self._strip_ansi(new_data.decode("utf-8", errors="replace"))
            if new_data
            else ""
        )
        pattern_in_new = bool(new_text and self.waiting_regex.search(new_text))

        if pattern_in_new:
            waiting_pattern_time = time.time()
        elif waiting_pattern_time is None:
            return False, None

        if waiting_pattern_time is not None:
            elapsed = time.time() - waiting_pattern_time
            if elapsed > self.waiting_expiry:
                tail = self._strip_ansi(
                    output_buffer[-512:].decode("utf-8", errors="replace")
                )
                if self.waiting_regex.search(tail):
                    waiting_pattern_time = time.time()
                else:
                    return False, None

        if not self.waiting_require_idle:
            return True, waiting_pattern_time

        if not (waiting_pattern_time and last_output_time):
            return False, waiting_pattern_time

        time_since_output = time.time() - last_output_time
        return time_since_output >= self.waiting_idle_timeout, waiting_pattern_time

    def check_idle_state(
        self,
        *,
        new_data: bytes,
        output_buffer: bytes,
        last_output_time: float | None,
        pattern_detected: bool,
        waiting_pattern_time: float | None,
        current_status: str,
        done_time: float | None,
        task_protection_active: bool,
        has_file_locks: bool,
    ) -> IdleStateEvaluation:
        pattern_match = self.check_pattern_idle(output_buffer, pattern_detected)
        pattern_detected = pattern_detected or pattern_match
        timeout_idle = self.check_timeout_idle(
            last_output_time=last_output_time,
            pattern_detected=pattern_detected,
        )
        is_idle = self.evaluate_idle_status(pattern_match, timeout_idle)
        is_waiting, waiting_pattern_time = self.check_waiting_state(
            new_data=new_data,
            output_buffer=output_buffer,
            last_output_time=last_output_time,
            waiting_pattern_time=waiting_pattern_time,
        )
        decision = self.determine_new_status(
            current_status=current_status,
            is_idle=is_idle,
            is_waiting=is_waiting,
            done_time=done_time,
            task_protection_active=task_protection_active,
            has_file_locks=has_file_locks,
        )
        return IdleStateEvaluation(
            pattern_match=pattern_match,
            timeout_idle=timeout_idle,
            is_idle=is_idle,
            is_waiting=is_waiting,
            new_status=decision.new_status,
            clear_done_time=decision.clear_done_time,
            pattern_detected=pattern_detected,
            waiting_pattern_time=waiting_pattern_time,
        )
