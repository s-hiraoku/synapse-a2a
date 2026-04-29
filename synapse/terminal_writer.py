from __future__ import annotations

import contextlib
import logging
import math
import os
import termios
import time
from collections.abc import Callable
from re import Pattern
from typing import Any

from synapse.status import DONE, PROCESSING, READY, WAITING


class TerminalWriter:
    """Handle PTY input injection and submit confirmation."""

    def __init__(
        self,
        owner: Any,
        *,
        agent_id: str | None,
        agent_type: str | None,
        write_delay: float,
        submit_retry_delay: float | None,
        bracketed_paste: bool,
        typing_char_delay: float,
        typing_max_chars: int,
        submit_confirm_timeout: float | None,
        submit_confirm_poll_interval: float | None,
        submit_confirm_retries: int,
        long_submit_confirm_timeout: float | None,
        long_submit_confirm_retries: int | None,
        copilot_compact_paste_re: Pattern[str],
        copilot_saved_paste_re: Pattern[str],
        kkp_disable_seq: bytes,
        copilot_submit_nudge_delay: float,
        copilot_long_submit_nudge_delay: float,
        copilot_paste_echo_poll: float,
        copilot_paste_echo_timeout: float,
        copilot_paste_echo_settle: float,
        strip_ansi: Callable[[str], str],
        logger: logging.Logger,
        os_module: Any = os,
        time_module: Any = time,
        termios_module: Any = termios,
        contextlib_module: Any = contextlib,
        math_module: Any = math,
    ) -> None:
        self.owner = owner
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.write_delay = write_delay
        self.submit_retry_delay = submit_retry_delay
        self.bracketed_paste = bracketed_paste
        self.typing_char_delay = typing_char_delay
        self.typing_max_chars = typing_max_chars
        self.submit_confirm_timeout = submit_confirm_timeout
        self.submit_confirm_poll_interval = submit_confirm_poll_interval
        self.submit_confirm_retries = submit_confirm_retries
        self.long_submit_confirm_timeout = long_submit_confirm_timeout
        self.long_submit_confirm_retries = long_submit_confirm_retries
        self._copilot_compact_paste_re = copilot_compact_paste_re
        self._copilot_saved_paste_re = copilot_saved_paste_re
        self._kkp_disable_seq = kkp_disable_seq
        self._copilot_submit_nudge_delay_value = copilot_submit_nudge_delay
        self._copilot_long_submit_nudge_delay_value = copilot_long_submit_nudge_delay
        self._copilot_paste_echo_poll = copilot_paste_echo_poll
        self._copilot_paste_echo_timeout = copilot_paste_echo_timeout
        self._copilot_paste_echo_settle = copilot_paste_echo_settle
        self._strip_ansi = strip_ansi
        self._logger = logger
        self._os = os_module
        self._time = time_module
        self._termios = termios_module
        self._contextlib = contextlib_module
        self._math = math_module

    @property
    def _write_lock(self) -> Any:
        return self.owner._write_lock

    @property
    def _status_lock(self) -> Any:
        return self.owner.lock

    def _os_module(self) -> Any:
        return self.owner._writer_os_module()

    def _time_module(self) -> Any:
        return self.owner._writer_time_module()

    def _termios_module(self) -> Any:
        return self.owner._writer_termios_module()

    def _contextlib_module(self) -> Any:
        return self.owner._writer_contextlib_module()

    def _math_module(self) -> Any:
        return self.owner._writer_math_module()

    @property
    def _icrnl_cleared(self) -> bool:
        return bool(self.owner._icrnl_cleared)

    @_icrnl_cleared.setter
    def _icrnl_cleared(self, value: bool) -> None:
        self.owner._icrnl_cleared = value

    @property
    def _kkp_disabled(self) -> bool:
        return bool(self.owner._kkp_disabled)

    @_kkp_disabled.setter
    def _kkp_disabled(self, value: bool) -> None:
        self.owner._kkp_disabled = value

    @staticmethod
    def _tail_text(text: str, limit: int = 4000) -> str:
        """Keep only the most recent visible context for prompt checks."""
        return text[-limit:]

    def _write_all(self, data: bytes) -> None:
        """Write all bytes to the PTY, retrying on partial writes."""
        fd = self.owner._inject_write_fd or self.owner.master_fd
        assert fd is not None
        total = len(data)
        written = 0
        while written < total:
            n = self._os_module().write(fd, data[written:])
            if n == 0:
                raise OSError("os.write returned 0, fd may be closed")
            written += n

    def _should_type_input(self, data: str, submit_seq: str | None) -> bool:
        """Whether to emulate real typing instead of bracketed paste."""
        return bool(
            self.agent_type != "copilot"
            and submit_seq
            and self.typing_max_chars > 0
            and len(data) <= self.typing_max_chars
            and "\n" not in data
            and "\r" not in data
        )

    def _write_typed_text(self, data: str) -> None:
        """Write text character-by-character to emulate actual keyboard input."""
        for idx, char in enumerate(data):
            self._write_all(char.encode("utf-8"))
            if self.typing_char_delay > 0 and idx + 1 < len(data):
                self._time_module().sleep(self.typing_char_delay)

    def _is_long_submit_message(self, data: str) -> bool:
        """Whether Copilot confirmation should use long-message heuristics."""
        if self.agent_type != "copilot":
            return False
        return "\n" in data or "\r" in data

    def _pending_submit_markers(self, data: str) -> list[str]:
        """Extract visible markers that indicate Copilot input still remains."""
        data_stripped = data.strip()
        if not data_stripped:
            return []

        markers: list[str] = [data_stripped]
        if "[LONG MESSAGE - FILE ATTACHED]" in data_stripped:
            markers.extend(
                [
                    "[LONG MESSAGE - FILE ATTACHED]",
                    "Please read this file",
                ]
            )
        elif self.owner._is_long_submit_message(data):
            lines = [line.strip() for line in data.splitlines() if line.strip()]
            for line in lines:
                if len(line) >= 8 and line not in markers:
                    markers.append(line)

        return markers

    def _has_copilot_pending_placeholder(self, current_tail: str) -> bool:
        """Whether Copilot still shows a paste placeholder after submit."""
        return any(
            pattern.search(current_tail)
            for pattern in (
                self._copilot_compact_paste_re,
                self._copilot_saved_paste_re,
            )
        )

    def _disable_kkp(self, reason: str, *, force: bool = False) -> None:
        """Disable Kitty Keyboard Protocol on the PTY."""
        if self.owner.master_fd is None or (self._kkp_disabled and not force):
            return
        try:
            with self._write_lock:
                if force or not self._kkp_disabled:
                    self._write_all(self._kkp_disable_seq)
                    self._kkp_disabled = True
                    self._logger.debug(f"[{self.agent_id}] KKP {reason}")
        except OSError:
            pass

    def _ensure_icrnl_disabled(self, submit_bytes: bytes) -> None:
        """Clear ICRNL on the PTY if sending CR and not already cleared."""
        if (
            submit_bytes == b"\r"
            and not self._icrnl_cleared
            and self.owner.master_fd is not None
        ):
            try:
                termios_module = self._termios_module()
                attrs = termios_module.tcgetattr(self.owner.master_fd)
                iflag = attrs[0]
                if iflag & termios_module.ICRNL:
                    attrs[0] = iflag & ~termios_module.ICRNL
                    termios_module.tcsetattr(
                        self.owner.master_fd,
                        termios_module.TCSANOW,
                        attrs,
                    )
                    self._logger.debug(f"[{self.agent_id}] ICRNL disabled for submit")
                self._icrnl_cleared = True
            except (self._termios_module().error, OSError):
                pass

    def _wait_for_copilot_paste_echo(self, pre_paste_context: str) -> None:
        """Wait for Copilot's Ink TUI to reflect the pasted text before Enter."""
        time_module = self._time_module()
        start = time_module.monotonic()
        deadline = start + self._copilot_paste_echo_timeout
        poll_count = 0
        while time_module.monotonic() < deadline:
            current = self.owner._tail_text(self._strip_ansi(self.owner.get_context()))
            poll_count += 1
            if current != pre_paste_context:
                elapsed = time_module.monotonic() - start
                self._logger.debug(
                    f"[{self.agent_id}] paste echo detected after {elapsed:.3f}s "
                    f"(polls={poll_count}), "
                    f"settling {self._copilot_paste_echo_settle}s for React state commit"
                )
                time_module.sleep(self._copilot_paste_echo_settle)
                return
            time_module.sleep(self._copilot_paste_echo_poll)
        self._logger.info(
            f"[{self.agent_id}] paste echo not detected within "
            f"{self._copilot_paste_echo_timeout}s (polls={poll_count}), "
            f"falling back to write_delay"
        )
        if self.write_delay > 0:
            time_module.sleep(self.write_delay)

    def write(self, data: str, submit_seq: str | None = None) -> bool:
        """Write data to the controlled process PTY with optional submit sequence."""
        if not self.owner.running:
            return False

        if self.owner.master_fd is None:
            raise ValueError(
                f"master_fd is None (interactive={self.owner.interactive})"
            )

        with self._status_lock:
            previous_status = self.owner.status
            self.owner.status = PROCESSING

        with self._write_lock:
            try:
                if (
                    self.agent_type == "copilot"
                    and not self.bracketed_paste
                    and "/" in data
                ):
                    data = "".join(
                        ("\uff0f" + line[1:]) if line.startswith("/") else line
                        for line in data.splitlines(keepends=True)
                    )
                pre_paste_context = self.owner._tail_text(
                    self._strip_ansi(self.owner.get_context())
                )
                pre_submit_context = (
                    pre_paste_context
                    if self.owner._should_confirm_submit(
                        data, submit_seq and submit_seq.encode("utf-8") or b""
                    )
                    else ""
                )
                use_typed_input = self.owner._should_type_input(data, submit_seq)
                if use_typed_input:
                    self.owner._write_typed_text(data)
                else:
                    data_bytes = data.encode("utf-8")
                    if self.bracketed_paste:
                        data_bytes = b"\x1b[200~" + data_bytes + b"\x1b[201~"
                    self._write_all(data_bytes)
                    if self.bracketed_paste and self.owner.master_fd is not None:
                        termios_module = self._termios_module()
                        with self._contextlib_module().suppress(
                            termios_module.error,
                            OSError,
                        ):
                            termios_module.tcdrain(self.owner.master_fd)
                if submit_seq:
                    submit_bytes = submit_seq.encode("utf-8")
                    if self.agent_type == "copilot" and self.bracketed_paste:
                        self.owner._wait_for_copilot_paste_echo(pre_paste_context)
                    elif self.write_delay > 0:
                        self._time_module().sleep(self.write_delay)
                    self.owner._ensure_icrnl_disabled(submit_bytes)
                    if not self._kkp_disabled and self.agent_type == "copilot":
                        self.owner._disable_kkp("proactively disabled")
                    self._write_all(submit_bytes)
                    if (
                        self.submit_retry_delay is not None
                        and not use_typed_input
                        and self.agent_type != "copilot"
                    ):
                        self._time_module().sleep(self.submit_retry_delay)
                        self._write_all(submit_bytes)
                    if pre_submit_context:
                        with self._status_lock:
                            self.owner.status = previous_status
                    self.owner._confirm_submit_if_needed(
                        data,
                        submit_bytes,
                        previous_status,
                        previous_context=pre_submit_context,
                    )
                return True
            except OSError as e:
                self._logger.error(f"Write to PTY failed: {e}")
                raise

    def _should_confirm_submit(self, data: str, submit_bytes: bytes) -> bool:
        """Whether submit confirmation should run for this write."""
        retries = self.submit_confirm_retries
        if (
            self.owner._is_long_submit_message(data)
            and self.long_submit_confirm_retries is not None
        ):
            retries = self.long_submit_confirm_retries
        return bool(
            data
            and submit_bytes
            and self.agent_type == "copilot"
            and self.submit_confirm_timeout is not None
            and self.submit_confirm_poll_interval is not None
            and retries > 0
        )

    def _copilot_submit_nudge_delay(self, data: str) -> float | None:
        """Return the short pre-confirmation Enter retry delay for Copilot."""
        if self.agent_type != "copilot":
            return None
        if (
            self.submit_confirm_timeout is None
            or self.submit_confirm_poll_interval is None
        ):
            return None
        return (
            self._copilot_long_submit_nudge_delay_value
            if self.owner._is_long_submit_message(data)
            else self._copilot_submit_nudge_delay_value
        )

    def _submit_confirmed(
        self, data: str, initial_status: str, previous_context: str
    ) -> bool:
        """Best-effort submit confirmation for Copilot PTY injections."""
        plain = self._strip_ansi(self.owner.get_context())
        current_tail = self.owner._tail_text(plain)
        markers = self.owner._pending_submit_markers(data)
        pending = any(marker in current_tail for marker in markers)
        if not pending and self.agent_type == "copilot":
            pending = self.owner._has_copilot_pending_placeholder(current_tail)

        current_status = self.owner.status
        if initial_status == READY and current_status != READY:
            return not pending
        if current_status in {PROCESSING, DONE}:
            return not pending
        if current_status == WAITING and initial_status != WAITING:
            return not pending

        if not markers:
            return True

        return not pending

    def _confirm_submit_if_needed(
        self,
        data: str,
        submit_bytes: bytes,
        initial_status: str,
        previous_context: str,
    ) -> None:
        """Retry submit for Copilot when injected text appears to remain pending."""
        if not self.owner._should_confirm_submit(data, submit_bytes):
            return

        assert self.submit_confirm_timeout is not None
        assert self.submit_confirm_poll_interval is not None
        confirm_timeout = self.submit_confirm_timeout
        confirm_retries = self.submit_confirm_retries
        if self.owner._is_long_submit_message(data):
            if self.long_submit_confirm_timeout is not None:
                confirm_timeout = self.long_submit_confirm_timeout
            if self.long_submit_confirm_retries is not None:
                confirm_retries = self.long_submit_confirm_retries

        poll_limit = max(
            1,
            self._math_module().ceil(
                confirm_timeout / self.submit_confirm_poll_interval
            ),
        )
        nudge_delay = self.owner._copilot_submit_nudge_delay(data)
        if nudge_delay is not None:
            self._time_module().sleep(nudge_delay)
            if not self.owner._submit_confirmed(data, initial_status, previous_context):
                self._write_all(submit_bytes)

        for attempt in range(confirm_retries + 1):
            for _ in range(poll_limit):
                if self.owner._submit_confirmed(data, initial_status, previous_context):
                    return
                self._time_module().sleep(self.submit_confirm_poll_interval)

            if attempt < confirm_retries:
                self._write_all(submit_bytes)

        if self.agent_type == "copilot":
            self.owner._disable_kkp(
                "force re-disabled on confirmation failure",
                force=True,
            )
            self._icrnl_cleared = False
            self.owner._ensure_icrnl_disabled(submit_bytes)
            self._write_all(submit_bytes)
            self._time_module().sleep(
                nudge_delay or self._copilot_submit_nudge_delay_value
            )
            if self.owner._submit_confirmed(data, initial_status, previous_context):
                self._logger.info(
                    f"[{self.agent_id}] submit recovered after KKP force-disable"
                )
                return

        plain = self._strip_ansi(self.owner.get_context())
        tail = self.owner._tail_text(plain)
        markers = self.owner._pending_submit_markers(data)
        has_placeholder = self.owner._has_copilot_pending_placeholder(tail)
        message = (
            f"[{self.agent_id}] submit confirmation failed after "
            f"{confirm_retries} retries"
        )
        self._logger.warning(message)
        self._logger.debug(
            f"[{self.agent_id}] submit_diag: "
            f"markers={markers!r} "
            f"has_placeholder={has_placeholder} "
            f"status={self.owner.status} "
            f"tail_last200={tail[-200:]!r}"
        )
        self.owner._log_inject(
            "WARN",
            f"submit confirmation failed retries={confirm_retries}",
        )
