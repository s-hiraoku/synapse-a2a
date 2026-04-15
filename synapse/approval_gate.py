"""Approval Gate — unified permission-request decision and dispatch.

When a child agent stops in WAITING (PTY permission prompt, clarification
question, confirmation dialog, etc.), the child's server notifies its
parent via A2A with a ``permission`` metadata block. Historically the
parent has been expected to inspect that notification manually and either
POST ``/tasks/<id>/permission/approve`` or send a clarification message.
This works for interactive human operators but leaves non-interactive
parents (workflow runners, nested spawns) silently deadlocked.

Approval Gate centralises the parent's response:

1. The parent's own agent server receives an incoming A2A message whose
   metadata carries a ``permission`` block.
2. It builds an :class:`ApprovalRequest` describing the child, the
   prompt, and the originating sender.
3. :func:`decide` consults the configured policy (global default +
   per-profile overrides) and returns an :class:`ApprovalDecision`.
4. :func:`apply` executes the decision: for APPROVE/DENY it calls the
   child's ``/tasks/<id>/permission/{approve,deny}`` endpoint; for
   ESCALATE it leaves the prompt alone so a human can intervene.

This lets spawn, team start, workflow run, and any other parent-driven
flow share one response mechanism rather than each rebuilding it.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import requests

logger = logging.getLogger(__name__)


# Substrings that identify a child stuck on a non-permission terminal
# state. Sending the profile's runtime_response (``y\r`` etc.) to these
# screens has no effect, so the Approval Gate must short-circuit to
# ESCALATE instead of entering an approve/re-escalate flood loop. The
# canonical example is the OpenAI usage-limit banner captured during
# the Step D diagnostic (2026-04-15): ``■ You've hit your usage limit.
# Upgrade to Pro (...) try again at Apr 17th, 2026 6:28 AM``.
_BLOCKED_STATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"hit your usage limit", re.IGNORECASE),
    re.compile(r"Upgrade to Pro", re.IGNORECASE),
    re.compile(r"try again at .+ (AM|PM)", re.IGNORECASE),
)


def _is_blocked_state(pty_context: str) -> bool:
    """True if *pty_context* looks like a non-permission terminal state.

    A ``True`` return means auto-approving would not unblock the child,
    so the gate must escalate to a human operator instead.
    """
    if not pty_context:
        return False
    return any(p.search(pty_context) for p in _BLOCKED_STATE_PATTERNS)


class ApprovalDecision(str, Enum):
    """Decision returned by the gate's policy engine."""

    APPROVE = "approve"
    """Send the profile's runtime_response to the child's PTY via the
    permission/approve endpoint. The child's auto_approve config decides
    what text is actually written."""

    DENY = "deny"
    """Send the profile's deny_response via the permission/deny endpoint."""

    ESCALATE = "escalate"
    """Leave the child blocked and surface the request to a human.
    Used when the request is ambiguous, outside policy, or explicitly
    flagged as needing human judgment."""


@dataclass(frozen=True)
class ApprovalRequest:
    """Structured permission request extracted from an A2A notification.

    The gate does not care *how* the request was obtained (whether from
    ``_on_status_change`` escalation, an incoming message metadata block,
    or a direct inspection of the child's task state). It only cares
    about the five fields below.
    """

    task_id: str
    endpoint: str
    target_agent_id: str
    target_agent_type: str
    pty_context: str = ""
    sender_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _load_policy() -> dict[str, Any]:
    """Read approval_gate policy from :mod:`synapse.settings`.

    Structure::

        {
            "enabled": True,
            "default_action": "approve",
            "profile_overrides": {"codex": "approve", "claude": "escalate"},
        }

    Any subset of keys may be present; missing keys fall back to built-in
    defaults. Errors reading settings degrade quietly to defaults so that
    a broken settings.json cannot lock the gate open or closed.
    """
    defaults: dict[str, Any] = {
        "enabled": True,
        "default_action": ApprovalDecision.APPROVE.value,
        "profile_overrides": {},
    }
    try:
        from synapse.settings import get_settings

        settings = get_settings()
        raw = settings.raw if hasattr(settings, "raw") else {}
    except Exception:  # broad: settings module optional at import time
        return defaults

    policy = raw.get("approval_gate") if isinstance(raw, dict) else None
    if not isinstance(policy, dict):
        return defaults

    merged = dict(defaults)
    if "enabled" in policy:
        merged["enabled"] = bool(policy["enabled"])
    if "default_action" in policy:
        action = str(policy["default_action"]).lower()
        if action in {d.value for d in ApprovalDecision}:
            merged["default_action"] = action
    overrides = policy.get("profile_overrides")
    if isinstance(overrides, dict):
        clean_overrides = {
            str(k): str(v).lower()
            for k, v in overrides.items()
            if str(v).lower() in {d.value for d in ApprovalDecision}
        }
        merged["profile_overrides"] = clean_overrides
    return merged


def decide(request: ApprovalRequest) -> ApprovalDecision:
    """Return the gate's decision for *request*.

    Policy order:
    1. If the gate is disabled, always escalate (preserves legacy manual
       parent intervention).
    2. If the child's ``pty_context`` matches a known blocked-state
       banner (e.g. OpenAI usage limit), escalate regardless of policy
       — approving would send ``y\\r`` to a modal that does not accept
       it and the child would re-escalate indefinitely.
    3. Per-profile override (keyed by ``target_agent_type``) wins over
       the default.
    4. Fall back to the configured ``default_action`` (approve unless
       settings say otherwise).
    """
    policy = _load_policy()
    if not policy.get("enabled", True):
        return ApprovalDecision.ESCALATE

    if _is_blocked_state(request.pty_context):
        logger.info(
            "approval_gate: blocked-state detected on task %s (%s); escalating",
            request.task_id,
            request.target_agent_id,
        )
        return ApprovalDecision.ESCALATE

    overrides: dict[str, str] = policy.get("profile_overrides") or {}
    override = overrides.get(request.target_agent_type)
    if override:
        try:
            return ApprovalDecision(override)
        except ValueError:
            logger.warning(
                "approval_gate: invalid override %r for profile %s",
                override,
                request.target_agent_type,
            )

    default_action = str(policy.get("default_action", "approve"))
    try:
        return ApprovalDecision(default_action)
    except ValueError:
        # Malformed settings value. Prefer the safe side (escalate to a
        # human) rather than silently auto-approving based on a typo —
        # mirrors the ``disabled`` branch above. The ``_load_policy`` loader
        # normally filters bad values out, so this path only fires when a
        # caller bypasses the loader (e.g., tests or direct monkeypatch).
        logger.warning(
            "approval_gate: invalid default_action %r, escalating",
            default_action,
        )
        return ApprovalDecision.ESCALATE


def apply(
    request: ApprovalRequest,
    decision: ApprovalDecision,
    *,
    timeout: float = 10.0,
) -> bool:
    """Execute *decision* against *request*.

    Returns True when the gate successfully acted (approve/deny HTTP call
    succeeded, or escalate logged the request). Network errors and 4xx
    responses return False so the caller can fall back to legacy escalation
    (e.g. leaving the prompt for a human operator).
    """
    if decision is ApprovalDecision.ESCALATE:
        logger.info(
            "approval_gate: escalating task %s on %s (pty=%r)",
            request.task_id,
            request.target_agent_id,
            (request.pty_context or "")[:160],
        )
        return True

    if not request.endpoint or not request.task_id:
        missing = []
        if not request.endpoint:
            missing.append("endpoint")
        if not request.task_id:
            missing.append("task_id")
        logger.warning(
            "approval_gate: cannot apply %s — missing %s "
            "(task_id=%r, endpoint=%r, target_agent_id=%r)",
            decision.value,
            ", ".join(missing),
            request.task_id,
            request.endpoint,
            request.target_agent_id,
        )
        return False

    path = (
        "permission/approve"
        if decision is ApprovalDecision.APPROVE
        else "permission/deny"
    )
    url = f"{request.endpoint.rstrip('/')}/tasks/{request.task_id}/{path}"
    try:
        resp = requests.post(url, timeout=timeout)
    except requests.RequestException as exc:
        logger.warning(
            "approval_gate: %s call to %s failed: %s", decision.value, url, exc
        )
        return False
    if resp.status_code >= 400:
        logger.warning(
            "approval_gate: %s on %s returned HTTP %s: %s",
            decision.value,
            url,
            resp.status_code,
            (resp.text or "")[:200],
        )
        return False
    logger.info(
        "approval_gate: %sd task %s on %s",
        decision.value,
        request.task_id,
        request.target_agent_id,
    )
    return True


def decide_and_apply(request: ApprovalRequest) -> tuple[ApprovalDecision, bool]:
    """Convenience: run ``decide`` then ``apply`` and return both results.

    The two-step variant is exposed so callers can log or trace the
    decision separately when they need to.
    """
    decision = decide(request)
    ok = apply(request, decision)
    return decision, ok


class EscalationDeduper:
    """Thread-safe TTL guard that collapses repeat escalations.

    The Step D diagnostic (2026-04-15) captured four distinct task_ids
    carrying the same blocked-state ``pty_context`` within a 4 second
    window — the child kept minting fresh tasks as each
    ``permission/approve`` failed to unblock the underlying modal.
    Pure task_id dedupe does not catch this because the task_ids are
    all different; the dedupe key must be
    ``(target_agent_id, hash(pty_context))`` so the same child stuck on
    the same screen cannot walk around the guard by cycling task ids.

    Empty ``pty_context`` values are never treated as duplicates — we
    cannot prove the child is in the same state, so suppression would
    be unsafe.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = float(ttl_seconds)
        self._clock = clock
        self._entries: dict[tuple[str, str], float] = {}
        self._lock = threading.Lock()

    def _key(self, request: ApprovalRequest) -> tuple[str, str] | None:
        if not request.pty_context:
            return None
        digest = hashlib.sha1(
            request.pty_context.encode("utf-8", errors="replace")
        ).hexdigest()
        return (request.target_agent_id, digest)

    def seen(self, request: ApprovalRequest) -> bool:
        """Record *request* and return True if it is a duplicate.

        Expired entries are swept opportunistically on each call so the
        map cannot grow without bound.
        """
        key = self._key(request)
        if key is None:
            return False
        now = self._clock()
        with self._lock:
            self._entries = {
                k: ts for k, ts in self._entries.items() if now - ts <= self._ttl
            }
            if key in self._entries:
                return True
            self._entries[key] = now
            return False


_default_deduper = EscalationDeduper(ttl_seconds=60.0)


def get_default_deduper() -> EscalationDeduper:
    """Return the process-wide escalation dedupe guard.

    Callers on the incoming-escalation path consult this before running
    ``decide_and_apply`` so a child stuck on the same blocked screen
    cannot flood the parent with identical escalations under different
    task ids. Tests may construct their own :class:`EscalationDeduper`
    directly; production code uses this singleton.
    """
    return _default_deduper


def request_from_a2a_metadata(
    *,
    task_id: str,
    endpoint: str,
    target_agent_id: str,
    target_agent_type: str,
    metadata: dict[str, Any] | None,
    sender_id: str | None = None,
) -> ApprovalRequest:
    """Build an :class:`ApprovalRequest` from task metadata.

    The permission block is expected under ``metadata["permission"]`` —
    that is the same shape ``_on_status_change`` already writes via
    ``_build_permission_metadata`` in :mod:`synapse.a2a_compat`.
    """
    permission = {}
    if isinstance(metadata, dict):
        candidate = metadata.get("permission")
        if isinstance(candidate, dict):
            permission = candidate
    pty_context = str(permission.get("pty_context", "") or "")
    return ApprovalRequest(
        task_id=task_id,
        endpoint=endpoint,
        target_agent_id=target_agent_id,
        target_agent_type=target_agent_type,
        pty_context=pty_context,
        sender_id=sender_id,
        metadata=dict(metadata) if isinstance(metadata, dict) else {},
    )
