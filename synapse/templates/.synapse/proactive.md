PROACTIVE MODE (Mandatory Synapse Feature Usage):

All Synapse coordination features MUST be used for EVERY task, regardless of size.
Skipping any step is a violation. Follow the checklist below.

--- BEFORE starting work ---
1. synapse tasks create "<subject>" -d "<description>"   - Register task on board
2. synapse memory search "<relevant keywords>"           - Check shared knowledge
3. synapse list                                          - Check available agents

--- DURING work ---
4. synapse file-safety lock <file>                       - Lock files before editing
5. synapse memory save <key> "<finding>" --tags <tags>   - Save discoveries immediately
6. synapse canvas post "<artifact title>" --body "<content>"  - Post artifacts/diagrams
7. For subtasks: synapse spawn/send to delegate          - Never do everything alone

--- AFTER completing work ---
8. synapse file-safety unlock <file>                     - Release all file locks
9. synapse tasks complete <task_id>                      - Mark task done on board
10. synapse broadcast "Completed: <summary>"             - Notify all agents
11. synapse canvas post "<summary title>" --body "<result>"  - Post completion summary

RULES:
- NEVER skip task board registration (step 1) — even for 1-line fixes
- ALWAYS lock files before editing in multi-agent setups (step 4)
- ALWAYS save useful findings to shared memory (step 5)
- ALWAYS post significant artifacts to canvas (steps 6, 11)
- For tasks with 2+ phases: delegate at least one phase to another agent
- For tasks touching 3+ files: use file-safety locks on ALL files
- Check synapse memory search before implementing — someone may have solved it
- After every milestone: broadcast progress to the team

PER-TASK CHECKLIST:
  [ ] Task board entry created
  [ ] Shared memory searched
  [ ] Available agents checked
  [ ] Files locked before editing
  [ ] Discoveries saved to memory
  [ ] Canvas artifacts posted
  [ ] Files unlocked after editing
  [ ] Task marked complete
  [ ] Completion broadcast sent
