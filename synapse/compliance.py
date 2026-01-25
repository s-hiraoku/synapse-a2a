"""
Synapse Compliance / Permissions Control

This module implements the compliance and permission control system for synapse-a2a,
based on the specification from Issue #159.

Key concepts:
- 3 modes: manual, prefill, auto
- Provider-level configuration: claude, codex, gemini, opencode, copilot
- Mode → capability mapping (inject, submit, confirm, route)
- Hierarchical settings: user (~/.synapse) + project (.synapse)
- Warning banner display based on ui.warningBanner setting
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.panel import Panel
from rich.text import Text

if TYPE_CHECKING:
    from rich.console import RenderableType

# Lazy import for pyperclip (may not be available in all environments)
pyperclip: Any = None

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

# Known providers (Section 6)
KNOWN_PROVIDERS: frozenset[str] = frozenset(
    ["claude", "codex", "gemini", "opencode", "copilot"]
)


# =============================================================================
# Enums (Section 5, 10)
# =============================================================================


class ComplianceMode(Enum):
    """Compliance modes for provider control.

    - manual: No automation (display/copy only)
    - prefill: Input injection allowed, but no submit/confirm/route
    - auto: Full automation (current behavior, backward compatible)
    """

    MANUAL = "manual"
    PREFILL = "prefill"
    AUTO = "auto"


class ActionType(Enum):
    """Action types for Policy Engine (Section 10).

    - PROPOSE_PROMPT: Display prompt to user (always allowed)
    - INJECT_INPUT: Write to provider's stdin/PTY
    - SUBMIT_INPUT: Send Enter/newline to execute
    - AUTO_CONFIRM: Respond to y/n prompts automatically
    - ROUTE_OUTPUT: Route output from one provider to another
    - EXEC_TOOL: Execute tool (fileWrite/shell/network)
    """

    PROPOSE_PROMPT = "propose_prompt"
    INJECT_INPUT = "inject_input"
    SUBMIT_INPUT = "submit_input"
    AUTO_CONFIRM = "auto_confirm"
    ROUTE_OUTPUT = "route_output"
    EXEC_TOOL = "exec_tool"


class Decision(Enum):
    """Policy engine decision types.

    - ALLOW: Action is permitted
    - REQUIRE_HUMAN: Action requires human confirmation
    - DENY: Action is not permitted
    """

    ALLOW = "allow"
    REQUIRE_HUMAN = "require_human"
    DENY = "deny"


class ComplianceBlockedError(Exception):
    """Exception raised when an action is blocked by compliance policy.

    Attributes:
        mode: The compliance mode that blocked the action.
        action: The action type that was blocked.
        message: Human-readable message describing the block.
    """

    def __init__(
        self, mode: str, action: ActionType, message: str | None = None
    ) -> None:
        self.mode = mode
        self.action = action
        self.message = (
            message or f"Action {action.value} blocked by compliance mode: {mode}"
        )
        super().__init__(self.message)


class WriteResult(Enum):
    """Result of a write operation to indicate compliance state.

    - SUCCESS: Write completed normally with submit
    - PREFILLED: Data injected but submit was suppressed (prefill mode)
    - NOT_RUNNING: Process not running, write failed
    """

    SUCCESS = "success"
    PREFILLED = "prefilled"
    NOT_RUNNING = "not_running"



# =============================================================================
# Capability Mapping (Section 5.1)
# =============================================================================

# Mode → capability mapping (fixed per spec)
MODE_CAPABILITIES: dict[str, dict[str, bool]] = {
    "manual": {
        "inject": False,
        "submit": False,
        "confirm": False,
        "route": False,
    },
    "prefill": {
        "inject": True,
        "submit": False,
        "confirm": False,
        "route": False,
    },
    "auto": {
        "inject": True,
        "submit": True,
        "confirm": True,
        "route": True,
    },
}


def get_mode_capabilities(mode: str) -> dict[str, bool]:
    """Get capability mapping for a mode.

    Args:
        mode: Mode name ('manual', 'prefill', 'auto')

    Returns:
        Dictionary of capability names to enabled status.
    """
    return MODE_CAPABILITIES.get(mode, MODE_CAPABILITIES["auto"]).copy()


# =============================================================================
# Settings Loading (Section 7)
# =============================================================================


def _load_json_file(path: Path) -> dict[str, Any]:
    """Load JSON file, returning empty dict on failure."""
    if not path.exists():
        return {}

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return dict(data)
            return {}
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load settings from {path}: {e}")
        return {}


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries, with override taking precedence."""
    result: dict[str, Any] = {}
    all_keys = set(base.keys()) | set(override.keys())

    for key in all_keys:
        base_value = base.get(key)
        override_value = override.get(key)

        if isinstance(base_value, dict) and isinstance(override_value, dict):
            result[key] = _merge_dicts(base_value, override_value)
        elif override_value is not None:
            result[key] = override_value
        elif base_value is not None:
            result[key] = base_value

    return result


@dataclass
class ComplianceSettings:
    """Compliance settings container.

    Manages mode configuration per provider and UI settings.
    """

    default_mode: str = "auto"
    providers: dict[str, dict[str, str]] = field(default_factory=dict)
    warning_banner: str = "always"
    _raw_settings: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def load(
        cls,
        user_root: Path | None = None,
        project_root: Path | None = None,
    ) -> ComplianceSettings:
        """Load and merge compliance settings from all scopes.

        Priority (highest to lowest):
        1. Project settings (<project_root>/.synapse/settings.json)
        2. User settings (<user_root>/.synapse/settings.json)
        3. Defaults

        Args:
            user_root: User home directory (default: ~)
            project_root: Project root directory (default: cwd)

        Returns:
            ComplianceSettings instance with merged settings.
        """
        if user_root is None:
            user_root = Path.home()
        if project_root is None:
            project_root = Path.cwd()

        user_settings_path = user_root / ".synapse" / "settings.json"
        project_settings_path = project_root / ".synapse" / "settings.json"

        # Start with defaults
        merged: dict[str, Any] = {
            "defaultMode": "auto",
            "providers": {},
            "ui": {"warningBanner": "always"},
        }

        # Load and merge user settings
        user_settings = _load_json_file(user_settings_path)
        if user_settings:
            merged = _merge_dicts(merged, user_settings)
            logger.debug(f"Loaded user compliance settings from {user_settings_path}")

        # Load and merge project settings (higher priority)
        project_settings = _load_json_file(project_settings_path)
        if project_settings:
            merged = _merge_dicts(merged, project_settings)
            logger.debug(
                f"Loaded project compliance settings from {project_settings_path}"
            )

        # Validate and warn about unknown providers
        providers = merged.get("providers", {})
        for provider_name in providers:
            if provider_name not in KNOWN_PROVIDERS:
                logger.warning(
                    f"Unknown provider '{provider_name}' in compliance settings. "
                    f"Known providers: {', '.join(sorted(KNOWN_PROVIDERS))}"
                )

        return cls(
            default_mode=merged.get("defaultMode", "auto"),
            providers=providers,
            warning_banner=merged.get("ui", {}).get("warningBanner", "always"),
            _raw_settings=merged,
        )

    def get_effective_mode(self, provider: str) -> str:
        """Get effective mode for a provider.

        Resolution order (Section 7.2):
        1. providers.<provider>.mode if exists
        2. defaultMode if exists
        3. 'auto' (default)

        Args:
            provider: Provider name (e.g., 'claude', 'codex')

        Returns:
            Effective mode string ('manual', 'prefill', 'auto')
        """
        provider_config = self.providers.get(provider, {})
        if "mode" in provider_config:
            return provider_config["mode"]
        return self.default_mode

    def has_any_auto_mode(self) -> bool:
        """Check if any provider effectively uses auto mode.

        Used for autoOnly banner display logic.

        Returns:
            True if default is auto OR no providers override away from auto.
        """
        if self.default_mode == "auto":
            return True

        # Check if any provider explicitly sets auto
        for provider_config in self.providers.values():
            if provider_config.get("mode") == "auto":
                return True

        return False

    def should_show_banner(self) -> bool:
        """Determine if warning banner should be shown.

        Based on ui.warningBanner setting (Section 8.3):
        - 'always': Always show
        - 'autoOnly': Show only if any provider uses auto mode
        - 'off': Never show

        Returns:
            True if banner should be displayed.
        """
        if self.warning_banner == "always":
            return True
        if self.warning_banner == "autoOnly":
            return self.has_any_auto_mode()
        # 'off' returns False, unknown values default to True
        return self.warning_banner != "off"

    def get_banner_data(self) -> dict[str, Any]:
        """Get structured banner data for display.

        Returns:
            Dictionary containing:
            - default_mode: The default mode
            - provider_overrides: Dict of provider -> mode for non-default modes
            - capabilities: Dict of capability -> enabled for default mode
            - warning_banner: The banner setting
        """
        capabilities = get_mode_capabilities(self.default_mode)

        provider_overrides: dict[str, str] = {}
        for provider, config in self.providers.items():
            if "mode" in config:
                provider_overrides[provider] = config["mode"]

        return {
            "default_mode": self.default_mode,
            "provider_overrides": provider_overrides,
            "capabilities": capabilities,
            "warning_banner": self.warning_banner,
        }

    def format_banner(self) -> str:
        """Format banner as plain text string.

        Returns:
            Formatted banner string.
        """
        data = self.get_banner_data()
        caps = data["capabilities"]

        # Build capability list
        enabled_caps = [k for k, v in caps.items() if v]
        caps_str = "/".join(enabled_caps) if enabled_caps else "none"

        # Build mode line
        mode_upper = data["default_mode"].upper()
        lines = [f"Mode: {mode_upper} ({caps_str} enabled)"]

        # Add default and overrides
        parts = [f"default={data['default_mode']}"]
        for provider, mode in sorted(data["provider_overrides"].items()):
            parts.append(f"{provider}={mode}")

        lines.append(" | ".join(parts))
        lines.append(f"Banner: {data['warning_banner']}")

        return "\n".join(lines)

    def format_banner_panel(self) -> RenderableType:
        """Format banner as Rich Panel for TUI display.

        Returns:
            Rich Panel renderable.
        """
        data = self.get_banner_data()
        caps = data["capabilities"]

        # Build capability list
        enabled_caps = [k for k, v in caps.items() if v]
        caps_str = "/".join(enabled_caps) if enabled_caps else "none"

        # Create text content
        text = Text()
        text.append("⚠ ", style="bold yellow")
        text.append(f"Mode: {data['default_mode'].upper()}", style="bold")
        text.append(f" ({caps_str} enabled)\n", style="dim")

        # Add default and overrides
        text.append(f"default={data['default_mode']}", style="cyan")
        for provider, mode in sorted(data["provider_overrides"].items()):
            text.append(" | ", style="dim")
            text.append(f"{provider}={mode}", style="yellow")

        return Panel(
            text,
            title="[bold]Compliance Mode[/bold]",
            border_style="yellow",
            padding=(0, 1),
        )


# =============================================================================
# Policy Engine (Section 10)
# =============================================================================


class PolicyEngine:
    """Policy engine for checking action permissions.

    Checks whether actions are allowed based on the current mode.
    """

    def __init__(self, mode: str) -> None:
        """Initialize policy engine with a mode.

        Args:
            mode: Compliance mode ('manual', 'prefill', 'auto')
        """
        self.mode = mode
        self.capabilities = get_mode_capabilities(mode)

    @classmethod
    def for_provider(cls, provider: str, settings: ComplianceSettings) -> PolicyEngine:
        """Create a PolicyEngine for a specific provider.

        Args:
            provider: Provider name (e.g., 'claude')
            settings: ComplianceSettings instance

        Returns:
            PolicyEngine configured for the provider's effective mode.
        """
        mode = settings.get_effective_mode(provider)
        return cls(mode=mode)

    def check(self, action: ActionType) -> Decision:
        """Check if an action is allowed.

        Args:
            action: The action type to check.

        Returns:
            Decision (ALLOW, REQUIRE_HUMAN, or DENY)
        """
        # PROPOSE_PROMPT is always allowed (display only)
        if action == ActionType.PROPOSE_PROMPT:
            return Decision.ALLOW

        # Map actions to capabilities
        action_capability_map: dict[ActionType, str] = {
            ActionType.INJECT_INPUT: "inject",
            ActionType.SUBMIT_INPUT: "submit",
            ActionType.AUTO_CONFIRM: "confirm",
            ActionType.ROUTE_OUTPUT: "route",
            ActionType.EXEC_TOOL: "submit",  # EXEC_TOOL follows submit rules
        }

        capability = action_capability_map.get(action)
        if capability is None:
            # Unknown action - deny by default
            return Decision.DENY

        if self.capabilities.get(capability, False):
            return Decision.ALLOW
        return Decision.DENY


# =============================================================================
# UX Helper Functions (Section 9)
# =============================================================================


def format_prefill_notification(content: str) -> str:
    """Format notification message for prefill mode.

    Args:
        content: The content that was prefilled.

    Returns:
        Notification message string.
    """
    # Truncate long content for preview
    preview = content[:50] + "..." if len(content) > 50 else content
    preview = preview.replace("\n", " ")
    return f"[Prefilled] Press Enter to send: {preview}"


def format_manual_display(content: str, clipboard_success: bool = True) -> str:
    """Format display message for manual mode.

    Args:
        content: The proposed prompt content.
        clipboard_success: Whether clipboard copy succeeded.

    Returns:
        Display message string.
    """
    lines = [
        "─" * 40,
        content,
        "─" * 40,
    ]
    if clipboard_success:
        lines.append("[Copied to clipboard] Paste manually and press Enter")
    else:
        lines.append("[Clipboard unavailable] Copy the above and paste manually")
    return "\n".join(lines)


def _get_pyperclip() -> Any:
    """Get pyperclip module, importing lazily.

    Returns:
        pyperclip module or None if not available.
    """
    global pyperclip
    if pyperclip is None:
        try:
            import pyperclip as _pyperclip

            pyperclip = _pyperclip
        except ImportError:
            logger.warning("pyperclip not available - clipboard functions disabled")
            return None
    return pyperclip


def copy_to_clipboard(content: str) -> bool:
    """Copy content to clipboard.

    Args:
        content: Content to copy.

    Returns:
        True if successful, False otherwise.
    """
    clip = _get_pyperclip()
    if clip is None:
        return False

    try:
        clip.copy(content)
        return True
    except Exception as e:
        logger.warning(f"Failed to copy to clipboard: {e}")
        return False


# =============================================================================
# Config TUI Integration
# =============================================================================


def get_compliance_schema() -> dict[str, Any]:
    """Get schema for compliance settings (for TUI).

    Returns:
        Schema dictionary describing available settings.
    """
    return {
        "defaultMode": {
            "type": "enum",
            "values": ["auto", "prefill", "manual"],
            "default": "auto",
            "description": "Default compliance mode for all providers",
        },
        "providers": {
            "type": "object",
            "description": "Provider-specific mode overrides",
            "properties": {
                provider: {
                    "type": "object",
                    "properties": {
                        "mode": {
                            "type": "enum",
                            "values": ["auto", "prefill", "manual"],
                        }
                    },
                }
                for provider in KNOWN_PROVIDERS
            },
        },
        "ui": {
            "warningBanner": {
                "type": "enum",
                "values": ["always", "autoOnly", "off"],
                "default": "always",
                "description": "When to show compliance warning banner",
            },
        },
    }


# =============================================================================
# Logging Integration
# =============================================================================


def log_compliance_banner(settings: ComplianceSettings) -> None:
    """Log compliance banner to logger.

    Args:
        settings: ComplianceSettings instance.
    """
    if not settings.should_show_banner():
        return

    data = settings.get_banner_data()
    caps = data["capabilities"]
    enabled_caps = [k for k, v in caps.items() if v]
    caps_str = "/".join(enabled_caps) if enabled_caps else "none"

    logger.info(f"Compliance Mode: {data['default_mode'].upper()} ({caps_str} enabled)")

    if data["provider_overrides"]:
        overrides = ", ".join(
            f"{p}={m}" for p, m in sorted(data["provider_overrides"].items())
        )
        logger.info(f"Provider overrides: {overrides}")
