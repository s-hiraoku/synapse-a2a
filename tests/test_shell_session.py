from __future__ import annotations

from pathlib import Path


def test_create_session_without_name(tmp_path: Path) -> None:
    from synapse.shell_session import ShellSessionStore

    store = ShellSessionStore(db_path=str(tmp_path / "shell_sessions.db"))

    session = store.create_session()

    assert session["id"]
    assert session["name"] is None
    assert session["created_at"]


def test_create_session_with_name(tmp_path: Path) -> None:
    from synapse.shell_session import ShellSessionStore

    store = ShellSessionStore(db_path=str(tmp_path / "shell_sessions.db"))

    session = store.create_session(name="debug session")

    assert session["name"] == "debug session"


def test_add_entry_supports_user_and_agent_roles(tmp_path: Path) -> None:
    from synapse.shell_session import ShellSessionStore

    store = ShellSessionStore(db_path=str(tmp_path / "shell_sessions.db"))
    session = store.create_session()

    user_entry = store.add_entry(session["id"], "user", "hello", agent_target="claude")
    agent_entry = store.add_entry(session["id"], "agent", "world")

    assert user_entry["role"] == "user"
    assert user_entry["agent_target"] == "claude"
    assert agent_entry["role"] == "agent"
    assert agent_entry["agent_target"] is None


def test_get_entries_returns_chronological_order(tmp_path: Path) -> None:
    from synapse.shell_session import ShellSessionStore

    store = ShellSessionStore(db_path=str(tmp_path / "shell_sessions.db"))
    session = store.create_session()
    store.add_entry(session["id"], "user", "first")
    store.add_entry(session["id"], "agent", "second")
    store.add_entry(session["id"], "user", "third")

    entries = store.get_entries(session["id"])

    assert [entry["content"] for entry in entries] == ["first", "second", "third"]


def test_list_sessions_returns_latest_first(tmp_path: Path) -> None:
    from synapse.shell_session import ShellSessionStore

    store = ShellSessionStore(db_path=str(tmp_path / "shell_sessions.db"))
    older = store.create_session(name="older")
    newer = store.create_session(name="newer")
    store.add_entry(older["id"], "user", "old content")
    store.add_entry(newer["id"], "user", "new content")

    sessions = store.list_sessions()

    assert sessions[0]["id"] == newer["id"]
    assert sessions[1]["id"] == older["id"]


def test_save_session_name_updates_existing_session(tmp_path: Path) -> None:
    from synapse.shell_session import ShellSessionStore

    store = ShellSessionStore(db_path=str(tmp_path / "shell_sessions.db"))
    session = store.create_session()

    updated = store.save_session_name(session["id"], "renamed")

    assert updated is True
    assert store.get_session(session["id"])["name"] == "renamed"


def test_sessions_are_isolated(tmp_path: Path) -> None:
    from synapse.shell_session import ShellSessionStore

    store = ShellSessionStore(db_path=str(tmp_path / "shell_sessions.db"))
    session_one = store.create_session(name="one")
    session_two = store.create_session(name="two")
    store.add_entry(session_one["id"], "user", "alpha")
    store.add_entry(session_two["id"], "user", "beta")

    entries_one = store.get_entries(session_one["id"])
    entries_two = store.get_entries(session_two["id"])

    assert [entry["content"] for entry in entries_one] == ["alpha"]
    assert [entry["content"] for entry in entries_two] == ["beta"]
