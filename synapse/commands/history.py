"""History command handlers for Synapse CLI."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

HISTORY_DISABLED_MSG = "History is disabled. Enable with: SYNAPSE_HISTORY_ENABLED=true"


def _get_history_manager() -> Any:
    """Get HistoryManager with settings env applied."""
    from synapse.history import HistoryManager
    from synapse.paths import get_history_db_path
    from synapse.settings import get_settings

    settings = get_settings()
    env_dict = dict(os.environ)
    settings.apply_env(env_dict)
    os.environ.update(env_dict)

    db_path = get_history_db_path()
    return HistoryManager.from_env(db_path=db_path)


def _print_history_table(observations: list[dict]) -> None:
    """Print observations in a formatted table."""
    hdr = f"{'Task ID':<36} {'Agent':<10} {'Status':<12} {'Timestamp':<19}"
    print(f"{hdr} {'Input (first 40 chars)':<42}")
    print("-" * 119)

    for obs in observations:
        task_id = obs["task_id"][:36]
        agent = obs["agent_name"][:10]
        status = obs["status"][:12]
        timestamp = obs["timestamp"][:19] if obs["timestamp"] else "N/A"
        input_preview = (
            obs["input"][:40].replace("\n", " ") if obs["input"] else "(empty)"
        )
        row = f"{task_id:<36} {agent:<10} {status:<12} {timestamp:<19}"
        print(f"{row} {input_preview:<42}")


def cmd_history_list(args: argparse.Namespace) -> None:
    """List task history."""
    from synapse import cli as cli_module

    manager = cli_module._get_history_manager()

    if not manager.enabled:
        print(HISTORY_DISABLED_MSG)
        return

    observations = manager.list_observations(
        limit=args.limit, agent_name=args.agent if args.agent else None
    )

    if not observations:
        print("No task history found.")
        return

    _print_history_table(observations)

    print(f"\nShowing {len(observations)} entries (limit: {args.limit})")
    if args.agent:
        print(f"Filtered by agent: {args.agent}")


def _print_observation_detail(observation: dict) -> None:
    """Print detailed observation information."""
    print(f"Task ID:        {observation['task_id']}")
    print(f"Agent:          {observation['agent_name']}")
    print(f"Status:         {observation['status']}")
    print(f"Session ID:     {observation['session_id']}")
    print(f"Timestamp:      {observation['timestamp']}")

    print("\n" + "=" * 80)
    print("INPUT:")
    print("=" * 80)
    print(observation["input"] or "(empty)")

    print("\n" + "=" * 80)
    print("OUTPUT:")
    print("=" * 80)
    print(observation["output"] or "(empty)")

    if observation.get("metadata"):
        print("\n" + "=" * 80)
        print("METADATA:")
        print("=" * 80)
        print(json.dumps(observation["metadata"], indent=2))


def cmd_history_show(args: argparse.Namespace) -> None:
    """Show detailed task information."""
    from synapse import cli as cli_module

    manager = cli_module._get_history_manager()

    if not manager.enabled:
        print(HISTORY_DISABLED_MSG)
        return

    observation = manager.get_observation(args.task_id)

    if not observation:
        print(f"Task not found: {args.task_id}")
        sys.exit(1)

    _print_observation_detail(observation)


def cmd_trace(args: argparse.Namespace) -> None:
    """Trace a task ID across A2A history and file-safety modification records."""
    from synapse import cli as cli_module
    from synapse.file_safety import FileSafetyManager

    manager = cli_module._get_history_manager()

    if not manager.enabled:
        print(HISTORY_DISABLED_MSG)
        return

    observation = manager.get_observation(args.task_id)
    if not observation:
        print(f"Task not found: {args.task_id}")
        sys.exit(1)

    _print_observation_detail(observation)

    fm = FileSafetyManager.from_env()
    if not fm.enabled:
        return

    mods = fm.get_modifications_by_task(observation["task_id"])
    if not mods:
        return

    print("\n" + "=" * 80)
    print("FILE MODIFICATIONS:")
    print("=" * 80)
    for mod in mods:
        ts = mod.get("timestamp", "N/A")
        agent = mod.get("agent_name", "unknown")
        change_type = mod.get("change_type", "MODIFY")
        path = mod.get("file_path", "")
        print(f"\n[{ts}] {agent} - {change_type}")
        if mod.get("intent"):
            print(f"  Intent: {mod['intent']}")
        if path:
            print(f"  File: {path}")


def cmd_history_search(args: argparse.Namespace) -> None:
    """Search task history by keywords."""
    from synapse import cli as cli_module

    manager = cli_module._get_history_manager()

    if not manager.enabled:
        print(HISTORY_DISABLED_MSG)
        return

    observations = manager.search_observations(
        keywords=args.keywords,
        logic=args.logic,
        case_sensitive=args.case_sensitive,
        limit=args.limit,
        agent_name=args.agent if args.agent else None,
    )

    if not observations:
        print(f"No matches found for: {', '.join(args.keywords)}")
        return

    _print_history_table(observations)

    print(f"\nFound {len(observations)} matches")
    print(f"Keywords: {', '.join(args.keywords)} (logic: {args.logic})")
    if args.agent:
        print(f"Filtered by agent: {args.agent}")


def cmd_history_cleanup(args: argparse.Namespace) -> None:
    """Clean up old task history."""
    from synapse import cli as cli_module

    manager = cli_module._get_history_manager()

    if not manager.enabled:
        print(HISTORY_DISABLED_MSG)
        return

    if args.days is None and args.max_size is None:
        print("Error: Specify --days or --max-size")
        sys.exit(1)

    if args.days is not None and args.max_size is not None:
        print("Error: Specify only one of --days or --max-size")
        sys.exit(1)

    if args.days is not None and args.days <= 0:
        print("Error: --days must be greater than 0")
        sys.exit(1)

    db_path = manager.db_path

    if args.dry_run:
        if args.days is not None:
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cutoff_sql = f"datetime('now', '-{args.days} days')"
                cursor.execute(
                    f"SELECT COUNT(*) FROM observations WHERE timestamp < {cutoff_sql}"
                )
                count = cursor.fetchone()[0]
                conn.close()
                print(f"Would delete {count} observations older than {args.days} days")
            except Exception as e:
                print(f"Error checking observations: {e}", file=sys.stderr)
        else:
            try:
                current_size_mb = Path(db_path).stat().st_size / (1024 * 1024)
                print(f"Current database size: {current_size_mb:.2f} MB")
                print(f"Target size: {args.max_size} MB")
                if current_size_mb > args.max_size:
                    print("Would delete oldest observations to reach target size")
                else:
                    print("No cleanup needed (already under target size)")
            except Exception as e:
                print(f"Error checking database: {e}", file=sys.stderr)
        return

    if not args.force:
        response = input(
            "This will permanently delete observations. Continue? (yes/no): "
        )
        if response.lower() not in ("yes", "y"):
            print("Cancelled.")
            return

    print("Cleaning up...")
    if args.days is not None:
        result = manager.cleanup_old_observations(
            days=args.days,
            vacuum=not args.no_vacuum,
        )
        count = result["deleted_count"]
        print(f"Deleted {count} observations older than {args.days} days")
    else:
        result = manager.cleanup_by_size(
            max_size_mb=args.max_size,
            vacuum=not args.no_vacuum,
        )
        print(f"Deleted {result['deleted_count']} observations to reach target size")

    if not args.no_vacuum and result["vacuum_reclaimed_mb"] > 0:
        print(f"Reclaimed {result['vacuum_reclaimed_mb']:.2f} MB of disk space")


def cmd_history_stats(args: argparse.Namespace) -> None:
    """Show task history statistics."""
    from synapse import cli as cli_module

    manager = cli_module._get_history_manager()

    if not manager.enabled:
        print(HISTORY_DISABLED_MSG)
        return

    stats = manager.get_statistics(agent_name=args.agent if args.agent else None)

    if not stats or stats["total_tasks"] == 0:
        print("No task history found.")
        return

    print("=" * 60)
    print("TASK HISTORY STATISTICS")
    print("=" * 60)
    print()

    print(f"Total Tasks:     {stats['total_tasks']}")
    print(f"Completed:       {stats['completed']}")
    print(f"Failed:          {stats['failed']}")
    print(f"Canceled:        {stats['canceled']}")
    print(f"Success Rate:    {stats['success_rate']:.1f}%")
    print()

    print(f"Database Size:   {stats['db_size_mb']:.2f} MB")
    if stats["oldest_task"]:
        print(f"Oldest Task:     {stats['oldest_task']}")
        print(f"Newest Task:     {stats['newest_task']}")
        print(f"Date Range:      {stats['date_range_days']} days")
    print()

    if stats["by_agent"]:
        print("=" * 60)
        print("BY AGENT")
        print("=" * 60)
        print()
        hdr = f"{'Agent':<10} {'Total':<8} {'Completed':<10} {'Failed':<8}"
        print(f"{hdr} {'Canceled':<8}")
        print("-" * 60)

        for agent, counts in sorted(stats["by_agent"].items()):
            print(
                f"{agent:<10} {counts['total']:<8} {counts['completed']:<10} "
                f"{counts['failed']:<8} {counts['canceled']:<8}"
            )
        print()

    try:
        token_stats = manager.get_token_statistics(
            agent_name=args.agent if args.agent else None
        )
        total_in = token_stats.get("total_input_tokens", 0)
        total_out = token_stats.get("total_output_tokens", 0)
        if total_in > 0 or total_out > 0:
            print("=" * 60)
            print("TOKEN USAGE")
            print("=" * 60)
            print()
            print(f"Input Tokens:    {total_in:,}")
            print(f"Output Tokens:   {total_out:,}")
            total_cost = token_stats.get("total_cost_usd", 0.0)
            print(f"Total Cost:      ${total_cost:.4f}")
            print()

            by_agent = token_stats.get("by_agent")
            if by_agent:
                hdr = f"{'Agent':<10} {'Input':<12} {'Output':<12} {'Cost':<10}"
                print(hdr)
                print("-" * 44)
                for agent, counts in sorted(by_agent.items()):
                    print(
                        f"{agent:<10} {counts.get('input_tokens', 0):<12,} "
                        f"{counts.get('output_tokens', 0):<12,} "
                        f"${counts.get('cost_usd', 0.0):<9.4f}"
                    )
                print()
    except Exception:
        pass

    if args.agent:
        print(f"(Filtered by agent: {args.agent})")


def cmd_history_export(args: argparse.Namespace) -> None:
    """Export task history in specified format."""
    from synapse import cli as cli_module

    manager = cli_module._get_history_manager()

    if not manager.enabled:
        print(HISTORY_DISABLED_MSG)
        return

    export_format = args.format.lower()
    if export_format not in ("json", "csv"):
        print(f"Error: Invalid format '{export_format}'. Use 'json' or 'csv'.")
        sys.exit(1)

    exported_data = manager.export_observations(
        format=export_format,
        agent_name=args.agent if args.agent else None,
        limit=args.limit if args.limit else None,
    )

    if args.output:
        try:
            with open(args.output, "w") as f:
                f.write(exported_data)
            print(f"Exported to {args.output}")
        except OSError as e:
            print(f"Error writing to file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(exported_data)
