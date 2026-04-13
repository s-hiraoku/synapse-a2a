---
description: 'Workflow: Post-implementation workflow using target: self. Runs docs/simplify/sync
  in parallel, then release, commit all changes, create PR, and autofix with pr-guardian
  — all injected back into the current agent''s own PTY. Mirrors post-impl-codex but
  stays in-process instead of spawning a separate agent.

  . Triggered by /post-impl command.'
name: post-impl
---
<!-- synapse-workflow-autogen -->

# post-impl

Auto-generated from workflow YAML. Do not edit — changes will be overwritten by `synapse workflow sync`.

## Instructions
Run: `synapse workflow run post-impl --auto-spawn`
