"""Skill evolution engine driven by learned instincts."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from synapse.instinct import InstinctStore

DEFAULT_EVOLVED_SKILLS_DIR = ".synapse/evolved/skills"


@dataclass
class SkillCandidate:
    """A generated skill candidate clustered from instincts."""

    name: str
    description: str
    domain: str
    instincts: list[dict[str, Any]]
    avg_confidence: float
    suggested_type: str


class EvolutionEngine:
    """Cluster instincts into reusable skill candidates."""

    def __init__(self, instinct_store: InstinctStore) -> None:
        self.instinct_store = instinct_store

    def find_skill_candidates(
        self, min_instincts: int = 2, min_avg_confidence: float = 0.5
    ) -> list[SkillCandidate]:
        """Aggregate instincts by domain and return viable skill candidates."""
        instincts = self.instinct_store.list(limit=1000)
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for instinct in instincts:
            domain = str(instinct.get("domain") or "").strip()
            if domain:
                grouped[domain].append(instinct)

        candidates: list[SkillCandidate] = []
        for domain, domain_instincts in grouped.items():
            if len(domain_instincts) < min_instincts:
                continue
            avg_confidence = round(
                sum(float(item["confidence"]) for item in domain_instincts)
                / len(domain_instincts),
                2,
            )
            if avg_confidence < min_avg_confidence:
                continue
            candidates.append(
                SkillCandidate(
                    name=f"{domain}-learned",
                    description=self._build_description(domain, domain_instincts),
                    domain=domain,
                    instincts=domain_instincts,
                    avg_confidence=avg_confidence,
                    suggested_type=self._suggested_type(domain, domain_instincts),
                )
            )
        return sorted(candidates, key=lambda item: item.avg_confidence, reverse=True)

    def generate_skill_md(self, candidate: SkillCandidate) -> str:
        """Render a skill candidate in SKILL.md format."""
        instinct_ids = [
            str(item["id"]) for item in candidate.instincts if item.get("id")
        ]
        trigger_lines = "\n".join(
            f"- {item['trigger']}"
            for item in candidate.instincts
            if item.get("trigger")
        )
        action_lines = "\n".join(
            f"- {item['action']}" for item in candidate.instincts if item.get("action")
        )
        title = candidate.name.replace("-", " ").title()
        return (
            "---\n"
            f"name: {candidate.name}\n"
            f'description: "{candidate.description}"\n'
            f"evolved_from: {json.dumps(instinct_ids)}\n"
            "---\n\n"
            f"# {title}\n\n"
            f"{candidate.description}\n\n"
            "## Triggers\n"
            f"{trigger_lines}\n\n"
            "## Actions\n"
            f"{action_lines}\n"
        )

    def evolve(
        self,
        generate: bool = False,
        output_dir: str | None = None,
    ) -> list[SkillCandidate]:
        """Find candidates and optionally write SKILL.md files to skill directories."""
        candidates = self.find_skill_candidates()
        if not generate:
            return candidates

        base_output = Path(output_dir or DEFAULT_EVOLVED_SKILLS_DIR)
        for candidate in candidates:
            content = self.generate_skill_md(candidate)
            skill_dirs = [
                base_output / candidate.name,
                Path(".claude") / "skills" / candidate.name,
                Path(".agents") / "skills" / candidate.name,
            ]
            for skill_dir in skill_dirs:
                _write_skill_file(skill_dir / "SKILL.md", content)
        return candidates

    @staticmethod
    def _build_description(domain: str, instincts: list[dict[str, Any]]) -> str:
        count = len(instincts)
        return (
            f"Learned {domain} patterns distilled from {count} instinct"
            f"{'' if count == 1 else 's'}."
        )

    @staticmethod
    def _suggested_type(domain: str, instincts: list[dict[str, Any]]) -> str:
        keywords = {"cli", "command", "shell", "terminal"}
        if domain == "commands":
            return "command"
        for instinct in instincts:
            trigger = str(instinct.get("trigger", "")).lower()
            action = str(instinct.get("action", "")).lower()
            if any(keyword in trigger or keyword in action for keyword in keywords):
                return "command"
        return "skill"


def _write_skill_file(path: Path, content: str) -> None:
    """Write content to a skill file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
