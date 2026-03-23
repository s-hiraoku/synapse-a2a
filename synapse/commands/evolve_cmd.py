"""Command helpers for learning instincts and evolving skills."""

from __future__ import annotations

from typing import Any

from synapse.evolve import EvolutionEngine
from synapse.instinct import InstinctStore
from synapse.observation import ObservationStore
from synapse.pattern_analyzer import PatternAnalyzer


def cmd_evolve(args: Any) -> None:
    """Run skill candidate discovery and optional generation."""
    store = InstinctStore.from_env(db_path=getattr(args, "db_path", None))
    engine = EvolutionEngine(store)
    candidates = engine.evolve(
        generate=bool(getattr(args, "generate", False)),
        output_dir=getattr(args, "output_dir", None),
    )
    if not candidates:
        print("No skill candidates found.")
        return
    for candidate in candidates:
        print(
            f"{candidate.name}: domain={candidate.domain} "
            f"avg_confidence={candidate.avg_confidence:.2f} "
            f"type={candidate.suggested_type}"
        )


def cmd_learn(args: Any) -> None:
    """Analyze observations and persist learned instincts."""
    observation_store = ObservationStore(
        db_path=getattr(args, "observation_db_path", None),
        enabled=True,
    )
    instinct_store = InstinctStore.from_env(db_path=getattr(args, "db_path", None))
    analyzer = PatternAnalyzer(observation_store, instinct_store)
    learned = analyzer.analyze_and_save(
        project_hash=getattr(args, "project_hash", None)
    )
    count = len(learned)
    noun = "instinct" if count == 1 else "instincts"
    print(f"Learned {count} {noun}.")


def cmd_instinct_status(args: Any) -> None:
    """Print instincts ordered by confidence."""
    store = InstinctStore.from_env(db_path=getattr(args, "db_path", None))
    instincts = store.list(
        scope=getattr(args, "scope", None),
        domain=getattr(args, "domain", None),
        min_confidence=getattr(args, "min_confidence", None),
        project_hash=getattr(args, "project_hash", None),
        limit=getattr(args, "limit", 50),
    )
    if not instincts:
        print("No instincts found.")
        return
    for instinct in instincts:
        print(
            f"{instinct['id']} confidence={instinct['confidence']:.2f} "
            f"scope={instinct['scope']} domain={instinct['domain'] or '-'} "
            f"trigger={instinct['trigger']} action={instinct['action']}"
        )


def cmd_instinct_promote(args: Any) -> None:
    """Promote a project instinct to global scope."""
    store = InstinctStore.from_env(db_path=getattr(args, "db_path", None))
    instinct_id = getattr(args, "instinct_id", None) or getattr(args, "id", None)
    if not instinct_id:
        raise ValueError("instinct_id is required")
    promoted = store.promote(str(instinct_id))
    if promoted:
        print(f"Promoted instinct {instinct_id}.")
        return
    print(f"Instinct {instinct_id} was not promoted.")
