PROACTIVE MODE (Mandatory Synapse Feature Usage):

All Synapse coordination features MUST be used for EVERY task, regardless of size.
Skipping any step is a violation. Follow the checklist below.

--- BEFORE starting work ---
1. synapse memory search "<relevant keywords>"           - Check shared knowledge
2. synapse list                                          - Check available agents

--- DURING work ---
3. synapse file-safety lock <file>                       - Lock files before editing
4. synapse memory save <key> "<finding>" --tags <tags>   - Save discoveries immediately
5. synapse canvas post "<artifact title>" --body "<content>"  - Post artifacts/diagrams
6. For subtasks: synapse spawn/send to delegate          - Never do everything alone

--- AFTER completing work ---
7. synapse file-safety unlock <file>                     - Release all file locks
8. synapse broadcast "Completed: <summary>"              - Notify all agents
9. synapse canvas post "<summary title>" --body "<result>"  - Post completion summary

RULES:
- ALWAYS lock files before editing in multi-agent setups (step 3)
- ALWAYS save useful findings to shared memory (step 4)
- ALWAYS post significant artifacts to canvas (steps 5, 9)
- For tasks with 2+ phases: delegate at least one phase to another agent
- For tasks touching 3+ files: use file-safety locks on ALL files
- Check synapse memory search before implementing — someone may have solved it
- After every milestone: broadcast progress to the team

PER-TASK CHECKLIST:
  [ ] Shared memory searched
  [ ] Available agents checked
  [ ] Files locked before editing
  [ ] Discoveries saved to memory
  [ ] Canvas artifacts posted
  [ ] Files unlocked after editing
  [ ] Completion broadcast sent
