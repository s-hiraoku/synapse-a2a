"""Shared memory command handlers for Synapse CLI."""

from __future__ import annotations

import argparse
import os
import sys

from synapse.a2a_client import A2AClient
from synapse.registry import AgentRegistry


def cmd_memory_save(args: argparse.Namespace) -> None:
    """Save a memory entry."""
    from synapse.shared_memory import SharedMemory

    mem = SharedMemory.from_env()
    tags = (
        [t.strip() for t in args.tags.split(",") if t.strip()]
        if getattr(args, "tags", None)
        else None
    )
    author = os.environ.get("SYNAPSE_AGENT_ID", "user")

    result = mem.save(
        key=args.key,
        content=args.content,
        author=author,
        tags=tags,
        scope=getattr(args, "scope", "global"),
    )
    if result:
        tag_str = f" [{', '.join(result['tags'])}]" if result["tags"] else ""
        scope_str = f" ({result['scope']})"
        print(f"Saved: {result['key']}{tag_str}{scope_str} (id: {result['id'][:8]})")
    else:
        print("Shared memory is disabled.", file=sys.stderr)
        sys.exit(1)

    if getattr(args, "notify", False):
        _memory_broadcast_notify(args.key)


def _memory_broadcast_notify(key: str) -> None:
    """Broadcast a notification about a saved memory."""
    try:
        registry = AgentRegistry()
        client = A2AClient()
        agents = registry.list_agents()
        current_working_dir = os.getcwd()
        my_id = os.environ.get("SYNAPSE_AGENT_ID", "")
        for agent_id, agent_info in agents.items():
            if agent_id != my_id:
                agent_wd = agent_info.get("working_dir")
                if agent_wd and agent_wd != current_working_dir:
                    continue
                name = agent_info.get("name") or agent_id
                endpoint = agent_info.get("endpoint", "")
                if not endpoint:
                    print(f"  Skipped: {name} (no endpoint)")
                    continue
                try:
                    task = client.send_to_local(
                        endpoint=endpoint,
                        message=f"Shared memory updated: {key}",
                        response_mode="silent",
                    )
                    if task is None:
                        print(f"  Failed: {name}: no response")
                    else:
                        print(f"  Notified: {name}")
                except Exception as e:  # broad catch: notification is best-effort
                    print(f"  Failed: {name}: {e}")
    except Exception as e:  # broad catch: broadcast is best-effort
        print(f"  Broadcast failed: {e}", file=sys.stderr)


def _resolve_memory_scope(
    args: argparse.Namespace,
) -> tuple[str, str | None, str | None]:
    """Resolve scope, working_dir, and author from CLI args."""
    scope = getattr(args, "scope", "global")
    working_dir = os.getcwd() if scope == "project" else None
    private_author = (
        os.environ.get("SYNAPSE_AGENT_ID", "user") if scope == "private" else None
    )
    return scope, working_dir, private_author


def cmd_memory_list(args: argparse.Namespace) -> None:
    """List memory entries."""
    from synapse.shared_memory import SharedMemory

    mem = SharedMemory.from_env()
    tags = (
        [t.strip() for t in args.tags.split(",") if t.strip()]
        if getattr(args, "tags", None)
        else None
    )
    limit = getattr(args, "limit", 50) or 50
    scope, working_dir, private_author = _resolve_memory_scope(args)

    items = mem.list_memories(
        author=private_author or getattr(args, "author", None),
        tags=tags,
        scope=scope,
        working_dir=working_dir,
        limit=limit,
    )

    if not items:
        print("No memories found.")
        return

    for item in items:
        tag_str = f" [{', '.join(item['tags'])}]" if item["tags"] else ""
        print(
            f"  {item['id'][:8]}  {item['key']}{tag_str}"
            f"  ({item['scope']})  by {item['author']}"
        )


def cmd_memory_show(args: argparse.Namespace) -> None:
    """Show memory details."""
    from synapse.shared_memory import SharedMemory

    mem = SharedMemory.from_env()
    item = mem.get(args.id_or_key)

    if not item:
        print(f"Memory not found: {args.id_or_key}", file=sys.stderr)
        sys.exit(1)

    print(f"Key:        {item['key']}")
    print(f"ID:         {item['id']}")
    print(f"Author:     {item['author']}")
    print(f"Scope:      {item['scope']}")
    if item.get("working_dir"):
        print(f"WorkingDir: {item['working_dir']}")
    print(f"Tags:       {', '.join(item['tags']) if item['tags'] else '(none)'}")
    print(f"Created:    {item['created_at']}")
    print(f"Updated:    {item['updated_at']}")
    print(f"\n{item['content']}")


def cmd_memory_search(args: argparse.Namespace) -> None:
    """Search memories."""
    from synapse.shared_memory import SharedMemory

    mem = SharedMemory.from_env()
    scope, working_dir, author = _resolve_memory_scope(args)
    results = mem.search(
        args.query,
        scope=scope,
        author=author,
        working_dir=working_dir,
    )

    if not results:
        print("No matching memories found.")
        return

    for item in results:
        tag_str = f" [{', '.join(item['tags'])}]" if item["tags"] else ""
        print(
            f"  {item['id'][:8]}  {item['key']}{tag_str}"
            f"  ({item['scope']})  by {item['author']}"
        )


def cmd_memory_delete(args: argparse.Namespace) -> None:
    """Delete a memory entry."""
    from synapse.shared_memory import SharedMemory

    if not getattr(args, "force", False):
        answer = input(f"Delete memory '{args.id_or_key}'? [y/N] ")
        if answer.lower() != "y":
            print("Cancelled.")
            return

    mem = SharedMemory.from_env()

    # Validate scope before deleting
    entry = mem.get(args.id_or_key)
    if not entry:
        print(f"Memory not found: {args.id_or_key}", file=sys.stderr)
        sys.exit(1)

    scope = entry.get("scope", "global")
    if scope == "private":
        my_id = os.environ.get("SYNAPSE_AGENT_ID", "")
        if entry.get("author") != my_id:
            print(
                f"Error: Cannot delete private memory owned by '{entry.get('author')}'",
                file=sys.stderr,
            )
            sys.exit(1)
    if (
        scope == "project"
        and entry.get("working_dir")
        and entry["working_dir"] != os.getcwd()
    ):
        print(
            "Error: Memory belongs to a different project directory",
            file=sys.stderr,
        )
        sys.exit(1)

    deleted = mem.delete(args.id_or_key)

    if deleted:
        print(f"Deleted: {args.id_or_key}")
    else:
        print(f"Failed to delete: {args.id_or_key}", file=sys.stderr)
        sys.exit(1)


def cmd_memory_stats(args: argparse.Namespace) -> None:
    """Show memory statistics."""
    from synapse.shared_memory import SharedMemory

    del args
    mem = SharedMemory.from_env()
    stats = mem.stats()

    print(f"Total memories: {stats['total']}")

    if stats["by_author"]:
        print("\nBy author:")
        for author, count in sorted(stats["by_author"].items()):
            print(f"  {author}: {count}")

    if stats["by_tag"]:
        print("\nBy tag:")
        for tag, count in sorted(stats["by_tag"].items()):
            print(f"  {tag}: {count}")
