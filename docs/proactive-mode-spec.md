# Synapse Proactive Mode

## Overview

Proactive Mode makes agents **always** use ALL Synapse features (shared memory, canvas, file safety, delegation, broadcast) for every task, regardless of size.

## Activation

```bash
# Environment variable
SYNAPSE_PROACTIVE_MODE_ENABLED=true synapse claude

# Or in .synapse/settings.json
{
  "env": {
    "SYNAPSE_PROACTIVE_MODE_ENABLED": "true"
  }
}
```

## Implementation

Follows the **learning_mode pattern** exactly: environment variable activation + supplementary `.synapse/proactive.md` instruction file appended at startup.

### Files Modified

| File | Change |
|------|--------|
| `synapse/settings.py` | Add env var, detection method, 3 integration points |
| `synapse/templates/.synapse/proactive.md` | Template (deployed by `synapse init`) |
| `.synapse/proactive.md` | Live copy (read by agents at runtime) |
| `tests/test_proactive_mode.py` | Tests following `test_learning_mode.py` pattern |

### settings.py Changes

1. **Env var** in `DEFAULT_SETTINGS["env"]`:
   ```python
   "SYNAPSE_PROACTIVE_MODE_ENABLED": "false",
   ```

2. **Detection method** (after `_is_shared_memory_enabled`):
   ```python
   def _is_proactive_mode_enabled(self) -> bool:
       return self._is_env_flag_enabled("SYNAPSE_PROACTIVE_MODE_ENABLED")
   ```

3. **Three integration points** (same pattern as shared-memory):
   - `_append_optional_instructions()`: load and append `proactive.md`
   - `get_instruction_files()`: add `"proactive.md"` to list
   - `get_instruction_file_paths()`: add via `add_if_exists("proactive.md")`

### proactive.md Content

Mandatory actions for EVERY task:
- **BEFORE**: `synapse memory search`, `synapse list`
- **DURING**: `synapse file-safety lock/unlock`, `synapse canvas post`, `synapse memory save`, delegation via `synapse spawn/send`
- **AFTER**: `synapse broadcast`, `synapse canvas post` summary
- Behavioral rules (always lock files, always post canvas artifacts)
- Per-task checklist

### Files NOT Modified

- `synapse/cli.py` — `_copy_synapse_templates` already copies all files via rglob
- `synapse/controller.py` — calls `get_instruction_file_paths()` which auto-includes
- `.synapse/default.md` — proactive.md adds rules on top, doesn't modify base
- Profile YAMLs — proactive mode is instruction-level, not detection-level

## Testing

```bash
pytest tests/test_proactive_mode.py -v        # New tests
pytest tests/test_learning_mode.py -v         # No regression
pytest tests/test_interactive_setup.py -v     # Template copy works
```

## Test Classes

- `TestProactiveModeSettings` — env var exists, default is "false"
- `TestProactiveModeInstructionInjection` — appended when enabled, not when disabled
- `TestProactiveModeFileList` — appears in file lists when enabled
- `TestProactiveModeTemplateExists` — template file exists with required sections
- `TestProactiveModeIndependence` — independent of learning mode, both can coexist
