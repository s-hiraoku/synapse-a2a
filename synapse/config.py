"""
Synapse A2A Configuration Constants

This module centralizes all magic numbers and configuration values
used throughout the codebase.
"""

# ============================================================
# Timeout Constants (in seconds)
# ============================================================

# Delay before sending initial instructions after agent startup
STARTUP_DELAY: int = 3

# Seconds of no output to consider agent idle/ready for input
OUTPUT_IDLE_THRESHOLD: float = 1.5

# Max wait time for identity instruction send
IDENTITY_WAIT_TIMEOUT: int = 10

# Delay after writing data before sending submit sequence (for TUI apps)
WRITE_PROCESSING_DELAY: float = 0.5

# Delay after write before checking idle state
POST_WRITE_IDLE_DELAY: float = 2.0

# HTTP request timeout: (connect_timeout, read_timeout)
REQUEST_TIMEOUT: tuple[int, int] = (3, 30)

# Timeout for port connectivity check
PORT_CHECK_TIMEOUT: float = 1.0

# Default timeout for waiting on agent task completion
AGENT_WAIT_TIMEOUT: int = 60

# Poll interval when waiting for task completion
TASK_POLL_INTERVAL: float = 1.0

# ============================================================
# Buffer Size Constants
# ============================================================

# Maximum size of output buffer (in characters/bytes)
OUTPUT_BUFFER_MAX: int = 10000

# Window size for idle state regex matching
# Increased from 1000 to 10000 to match full buffer for better idle detection
# especially for agents with large startup output (e.g., Claude Code)
IDLE_CHECK_WINDOW: int = 10000

# Recent context size for error detection and artifact generation
CONTEXT_RECENT_SIZE: int = 3000

# Context size for API response
API_RESPONSE_CONTEXT_SIZE: int = 2000

# ============================================================
# Terminal States
# ============================================================

# Task states that indicate completion (no need to wait further)
COMPLETED_TASK_STATES: frozenset[str] = frozenset(
    {
        "completed",
        "failed",
        "canceled",
    }
)
