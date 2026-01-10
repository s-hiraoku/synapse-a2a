# Delegation Modes

## Session Startup Behavior

At session startup, check for existing delegation configuration:

```bash
cat ~/.synapse/delegation.md 2>/dev/null
```

If configuration exists:

1. Display current delegation mode and rules summary to user
2. Ask user: "Delegation settings found. Use these settings?"
3. If confirmed, apply the delegation rules to current session

## Setup Workflow

When user invokes `/delegate` or `/delegate <mode>`:

### Step 1: Select Mode

If mode not specified, ask user to choose:

- orchestrator: Analyze and integrate (recommended)
- passthrough: Direct forwarding
- off: Disable

### Step 2: Define Rules (Natural Language)

Prompt user for delegation rules:

```
Please describe your delegation rules in natural language.

Examples:
- Coding tasks (file editing, creation, refactoring) go to Codex
- Research and web searches go to Gemini
- Code reviews stay with Claude
```

### Step 3: Save Configuration

```bash
mkdir -p ~/.synapse
cat > ~/.synapse/delegation.md << 'EOF'
# Delegation Configuration

mode: <selected_mode>

## Rules
<user's natural language rules>
EOF
```

### Step 4: Confirm and Apply

Display saved configuration and confirm activation.

## Orchestrator Mode Workflow

```
1. Analyze user request
2. Run pre-delegation checklist
3. If target agent not READY:
   a. Inform user: "Target agent (<agent>) is processing. Wait?"
   b. Wait or queue based on user preference
4. If matches delegation rule and agent is READY:
   a. Acquire file locks if needed (File Safety)
   b. Send to target agent with appropriate priority
   c. Wait for response (monitor with synapse list --watch)
   d. Review and integrate response
   e. Release file locks
   f. Report final result to user
5. If no match: Process directly
```

## Passthrough Mode Workflow

```
1. Analyze user request
2. Check agent availability (skip if not READY)
3. If matches delegation rule:
   a. Forward to target agent with original request
   b. Relay response directly to user
4. If no match: Process directly
```

## Applying Delegation Rules

When delegation is active:

1. **Analyze the request** against configured rules
2. **Run pre-delegation checklist** (agent status, file locks)
3. **Determine target agent** (codex, gemini, or self)
4. **Select priority level** based on urgency
5. **Execute delegation** with appropriate method

## A2A Communication Methods

### Method 1: @Agent Pattern (Simple)

```
@codex Please refactor this file
@gemini Research this API
```

### Method 2: A2A Tool (Advanced)

```bash
python3 synapse/tools/a2a.py send --target <agent> --priority <1-5> "<message>"
```

Examples:
```bash
# Normal task (priority 3)
python3 synapse/tools/a2a.py send --target codex --priority 3 "Refactor src/auth.py"

# Urgent follow-up (priority 4)
python3 synapse/tools/a2a.py send --target gemini --priority 4 "Status update?"

# Critical task (priority 5)
python3 synapse/tools/a2a.py send --target codex --priority 5 "URGENT: Fix production bug"
```

## Configuration File Format

`~/.synapse/delegation.md`:

```markdown
# Delegation Configuration

mode: orchestrator

## Rules

Coding tasks (file editing, creation) go to Codex.
Research, web searches, documentation go to Gemini.
Code reviews, design decisions stay with Claude.

## File Safety

Check lock status before delegating file edits.

## Priority Guidelines

- Normal tasks: priority 3
- Follow-ups: priority 4
- Emergencies: priority 5
```
