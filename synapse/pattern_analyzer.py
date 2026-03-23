"""Rule-based analyzer that turns observations into instincts."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from synapse.instinct import InstinctStore
from synapse.observation import ObservationStore


def _confidence_for_count(count: int) -> float:
    """Map observation frequency to instinct confidence."""
    if count >= 10:
        return 0.9
    if count >= 5:
        return 0.7
    if count >= 3:
        return 0.5
    return 0.3


class PatternAnalyzer:
    """Analyze observations and generate instinct candidates."""

    def __init__(
        self, observation_store: ObservationStore, instinct_store: InstinctStore
    ) -> None:
        self.observation_store = observation_store
        self.instinct_store = instinct_store

    def analyze(
        self, project_hash: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Analyze observations and return instinct candidates."""
        observations = self.observation_store.list(
            project_hash=project_hash, limit=limit
        )
        candidates: list[dict[str, Any]] = []
        candidates.extend(self._analyze_repeated_errors(observations))
        candidates.extend(self._analyze_successful_senders(observations))
        candidates.extend(self._analyze_status_transitions(observations))
        return candidates

    def analyze_and_save(self, project_hash: str | None = None) -> list[dict[str, Any]]:
        """Analyze current observations and save/update instincts."""
        candidates = self.analyze(project_hash=project_hash)
        saved: list[dict[str, Any]] = []
        for candidate in candidates:
            existing = self.instinct_store.find_by_trigger_action(
                candidate["trigger"],
                candidate["action"],
                project_hash=project_hash,
            )
            if existing:
                new_confidence = max(existing["confidence"], candidate["confidence"])
                merged_sources = sorted(
                    set(existing["source_observations"])
                    | set(candidate["source_observations"])
                )
                self.instinct_store.update_confidence(existing["id"], new_confidence)
                self.instinct_store.update_sources(existing["id"], merged_sources)
                refreshed = self.instinct_store.get(existing["id"])
                if refreshed:
                    saved.append(refreshed)
            else:
                created = self.instinct_store.save(
                    trigger=candidate["trigger"],
                    action=candidate["action"],
                    confidence=candidate["confidence"],
                    scope="project",
                    domain=candidate["domain"],
                    source_observations=candidate["source_observations"],
                    project_hash=project_hash,
                    agent_id=candidate.get("agent_id"),
                )
                if created:
                    saved.append(created)
        return saved

    def _analyze_repeated_errors(
        self, observations: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for obs in observations:
            if obs["event_type"] != "error":
                continue
            error_type = str(obs["data"].get("error_type", "")).strip()
            if error_type:
                buckets[error_type].append(obs)

        candidates: list[dict[str, Any]] = []
        for error_type, items in buckets.items():
            if len(items) < 2:
                continue
            recovery = next(
                (
                    str(item["data"].get("recovery_action", "")).strip()
                    for item in items
                    if item["data"].get("recovery_action")
                ),
                "investigate the repeated failure pattern",
            )
            candidates.append(
                {
                    "trigger": f"{error_type} occurs repeatedly",
                    "action": recovery,
                    "domain": "debugging",
                    "confidence": _confidence_for_count(len(items)),
                    "source_observations": [item["id"] for item in items],
                    "agent_id": items[-1]["agent_id"],
                }
            )
        return candidates

    def _analyze_successful_senders(
        self, observations: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        received_by_sender: dict[str, list[dict[str, Any]]] = defaultdict(list)
        completed_by_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for obs in observations:
            if obs["event_type"] == "task_received":
                sender = str(obs["data"].get("sender", "")).strip()
                if sender:
                    received_by_sender[sender].append(obs)
            elif obs["event_type"] == "task_completed":
                if obs["data"].get("status") == "completed":
                    completed_by_agent[obs["agent_id"]].append(obs)

        candidates: list[dict[str, Any]] = []
        for sender, received_items in received_by_sender.items():
            successful_pairs = [
                obs for obs in received_items if completed_by_agent.get(obs["agent_id"])
            ]
            if len(successful_pairs) < 2:
                continue
            candidates.append(
                {
                    "trigger": f"tasks from {sender} consistently complete successfully",
                    "action": f"reuse the proven collaboration pattern for {sender}",
                    "domain": "testing",
                    "confidence": _confidence_for_count(len(successful_pairs)),
                    "source_observations": [item["id"] for item in successful_pairs],
                    "agent_id": successful_pairs[-1]["agent_id"],
                }
            )
        return candidates

    def _analyze_status_transitions(
        self, observations: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for obs in observations:
            if obs["event_type"] != "status_change":
                continue
            from_status = str(obs["data"].get("from_status", "")).strip()
            to_status = str(obs["data"].get("to_status", "")).strip()
            if from_status and to_status:
                buckets[(from_status, to_status)].append(obs)

        candidates: list[dict[str, Any]] = []
        for (from_status, to_status), items in buckets.items():
            if len(items) < 2:
                continue
            candidates.append(
                {
                    "trigger": f"status transitions frequently from {from_status} to {to_status}",
                    "action": f"optimize workflow around the {from_status}->{to_status} transition",
                    "domain": "workflow",
                    "confidence": _confidence_for_count(len(items)),
                    "source_observations": [item["id"] for item in items],
                    "agent_id": items[-1]["agent_id"],
                }
            )
        return candidates
