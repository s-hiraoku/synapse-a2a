from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from synapse.instinct import InstinctStore
from synapse.observation import ObservationStore


def test_find_skill_candidates_groups_instincts_by_domain(tmp_path: Path) -> None:
    from synapse.evolve import EvolutionEngine

    store = InstinctStore(db_path=str(tmp_path / "instincts.db"))
    store.save(
        trigger="debugging issue repeats",
        action="capture logs before retrying",
        confidence=0.8,
        domain="debugging",
        source_observations=["obs-1"],
    )
    store.save(
        trigger="timeout repeats",
        action="check network conditions",
        confidence=0.6,
        domain="debugging",
        source_observations=["obs-2"],
    )
    store.save(
        trigger="single testing pattern",
        action="run focused regression tests",
        confidence=0.9,
        domain="testing",
        source_observations=["obs-3"],
    )

    candidates = EvolutionEngine(store).find_skill_candidates()

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.name == "debugging-learned"
    assert candidate.domain == "debugging"
    assert candidate.avg_confidence == 0.7
    assert candidate.suggested_type == "skill"
    assert len(candidate.instincts) == 2


def test_find_skill_candidates_respects_min_avg_confidence(tmp_path: Path) -> None:
    from synapse.evolve import EvolutionEngine

    store = InstinctStore(db_path=str(tmp_path / "instincts.db"))
    store.save(
        trigger="workflow starts often",
        action="prepare shared checklist",
        confidence=0.4,
        domain="workflow",
        source_observations=["obs-1"],
    )
    store.save(
        trigger="workflow ends often",
        action="summarize the outcome",
        confidence=0.5,
        domain="workflow",
        source_observations=["obs-2"],
    )

    candidates = EvolutionEngine(store).find_skill_candidates(min_avg_confidence=0.6)

    assert candidates == []


def test_generate_skill_md_formats_frontmatter_and_sections(
    tmp_path: Path,
) -> None:
    from synapse.evolve import EvolutionEngine, SkillCandidate

    store = InstinctStore(db_path=str(tmp_path / "instincts.db"))
    candidate = SkillCandidate(
        name="debugging-learned",
        description="Learned debugging patterns for repeated failures.",
        domain="debugging",
        instincts=[
            {
                "id": "inst-1",
                "trigger": "error occurs repeatedly",
                "action": "collect the failing logs",
            },
            {
                "id": "inst-2",
                "trigger": "timeout occurs repeatedly",
                "action": "inspect upstream latency",
            },
        ],
        avg_confidence=0.7,
        suggested_type="skill",
    )

    content = EvolutionEngine(store).generate_skill_md(candidate)

    assert content.startswith("---\nname: debugging-learned\n")
    assert "description: Learned debugging patterns for repeated failures.\n" in content
    assert 'evolved_from: ["inst-1", "inst-2"]\n' in content
    assert "# Debugging Learned\n" in content
    assert (
        "## Triggers\n- error occurs repeatedly\n- timeout occurs repeatedly\n"
        in content
    )
    assert (
        "## Actions\n- collect the failing logs\n- inspect upstream latency\n"
        in content
    )


def test_evolve_generate_writes_skill_files(tmp_path: Path, monkeypatch) -> None:
    from synapse.evolve import EvolutionEngine

    root = tmp_path
    monkeypatch.chdir(root)
    store = InstinctStore(db_path=str(root / ".synapse" / "instincts.db"))
    store.save(
        trigger="debugging issue repeats",
        action="capture logs before retrying",
        confidence=0.8,
        domain="debugging",
        source_observations=["obs-1"],
    )
    store.save(
        trigger="timeout repeats",
        action="check network conditions",
        confidence=0.6,
        domain="debugging",
        source_observations=["obs-2"],
    )

    candidates = EvolutionEngine(store).evolve(generate=True)

    assert len(candidates) == 1
    skill_name = candidates[0].name
    evolved_file = root / ".synapse" / "evolved" / "skills" / skill_name / "SKILL.md"
    claude_file = root / ".claude" / "skills" / skill_name / "SKILL.md"
    agents_file = root / ".agents" / "skills" / skill_name / "SKILL.md"
    assert evolved_file.exists()
    assert claude_file.exists()
    assert agents_file.exists()
    assert (
        evolved_file.read_text() == claude_file.read_text() == agents_file.read_text()
    )


def test_cmd_learn_turns_observations_into_instincts(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    from synapse.commands.evolve_cmd import cmd_learn

    root = tmp_path
    monkeypatch.chdir(root)
    observation_store = ObservationStore(
        db_path=str(root / ".synapse" / "observations.db")
    )
    for index in range(2):
        observation_store.save(
            event_type="error",
            agent_id="synapse-codex-9000",
            data={
                "error_type": "TimeoutError",
                "recovery_action": "inspect the upstream latency",
                "attempt": index,
            },
            project_hash="proj-1",
        )

    args = Namespace(
        db_path=str(root / ".synapse" / "instincts.db"),
        observation_db_path=str(root / ".synapse" / "observations.db"),
        project_hash="proj-1",
    )

    cmd_learn(args)

    instincts = InstinctStore(db_path=args.db_path).list(project_hash="proj-1")
    output = capsys.readouterr().out
    assert len(instincts) == 1
    assert instincts[0]["trigger"] == "TimeoutError occurs repeatedly"
    assert "learned 1 instinct" in output.lower()
