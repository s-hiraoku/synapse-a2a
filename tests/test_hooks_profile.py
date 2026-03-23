from __future__ import annotations


def test_minimal_profile_disables_all_hooks() -> None:
    from synapse.hooks import HookManager

    manager = HookManager(
        hooks_config={
            "on_idle": "echo idle",
            "on_task_completed": "echo complete",
            "on_status_change": "echo status",
        },
        profile="minimal",
    )

    assert manager.get_profile() == "minimal"
    assert manager.get_hook("on_idle") == ""
    assert manager.get_hook("on_task_completed") == ""
    assert manager.get_hook("on_status_change") == ""


def test_standard_profile_only_allows_task_completed() -> None:
    from synapse.hooks import HookManager

    manager = HookManager(
        hooks_config={
            "on_idle": "echo idle",
            "on_task_completed": "echo complete",
            "on_status_change": "echo status",
        },
        profile="standard",
    )

    assert manager.get_hook("on_idle") == ""
    assert manager.get_hook("on_task_completed") == "echo complete"
    assert manager.get_hook("on_status_change") == ""


def test_strict_profile_allows_all_profile_hooks() -> None:
    from synapse.hooks import HookManager

    manager = HookManager(
        hooks_config={
            "on_idle": "echo idle",
            "on_task_completed": "echo complete",
            "on_status_change": "echo status",
        },
        profile="strict",
    )

    assert manager.get_hook("on_idle") == "echo idle"
    assert manager.get_hook("on_task_completed") == "echo complete"
    assert manager.get_hook("on_status_change") == "echo status"


def test_env_profile_overrides_constructor(monkeypatch) -> None:
    from synapse.hooks import HookManager

    monkeypatch.setenv("SYNAPSE_HOOK_PROFILE", "minimal")
    manager = HookManager(
        hooks_config={"on_task_completed": "echo complete"},
        profile="strict",
    )

    assert manager.get_profile() == "minimal"
    assert manager.get_hook("on_task_completed") == ""


def test_env_disabled_hooks_override_enabled_profile(monkeypatch) -> None:
    from synapse.hooks import HookManager

    monkeypatch.setenv("SYNAPSE_DISABLED_HOOKS", "on_task_completed,on_idle")
    manager = HookManager(
        hooks_config={
            "on_idle": "echo idle",
            "on_task_completed": "echo complete",
            "on_status_change": "echo status",
        },
        profile="strict",
    )

    assert manager.get_hook("on_idle") == ""
    assert manager.get_hook("on_task_completed") == ""
    assert manager.get_hook("on_status_change") == "echo status"


def test_disabled_hooks_argument_works_with_profile() -> None:
    from synapse.hooks import HookManager

    manager = HookManager(
        hooks_config={
            "on_idle": "echo idle",
            "on_task_completed": "echo complete",
            "on_status_change": "echo status",
        },
        profile="strict",
        disabled_hooks=["on_status_change"],
    )

    assert manager.get_hook("on_idle") == "echo idle"
    assert manager.get_hook("on_task_completed") == "echo complete"
    assert manager.get_hook("on_status_change") == ""


def test_profile_hooks_still_override_base_config() -> None:
    from synapse.hooks import HookManager

    manager = HookManager(
        hooks_config={"on_task_completed": "echo base"},
        profile_hooks={"on_task_completed": "echo override"},
        profile="standard",
    )

    assert manager.get_hook("on_task_completed") == "echo override"


def test_profile_none_preserves_existing_behavior() -> None:
    from synapse.hooks import HookManager

    manager = HookManager(
        hooks_config={
            "on_idle": "echo idle",
            "on_task_completed": "echo complete",
            "on_status_change": "echo status",
        }
    )

    assert manager.get_profile() == "standard"
    assert manager.get_hook("on_idle") == "echo idle"
    assert manager.get_hook("on_task_completed") == "echo complete"
    assert manager.get_hook("on_status_change") == "echo status"
