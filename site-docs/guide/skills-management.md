# Skills Management

Synapse A2A's skills are distributed via GitHub CLI's built-in
**Agent Skills** command (`gh skill`) as of 2026-04-18. This is the
canonical way to install, pin, update, and publish skills for this
project.

- Announcement: <https://github.blog/changelog/2026-04-16-manage-agent-skills-with-github-cli/>
- Spec: <https://agentskills.io>
- Minimum `gh` CLI version: **2.90.0**

## Why `gh skill`

- **Version pinning** — `gh skill install <repo> <skill> --pin <ref>`
  locks to a specific tag or SHA. Pinned skills are skipped by
  `gh skill update`.
- **Provenance metadata** — each installed `SKILL.md` records the
  source repository, ref, and tree SHA in its frontmatter, so drift
  is detectable.
- **Cross-agent portability** — `--agent <name>` targets a specific
  runtime (`claude-code`, `copilot`, `cursor`, etc.); one source of
  truth, many agent targets.
- **Supply-chain hygiene** — centralised install path replaces the
  ad-hoc `cp -r` distribution that used to copy skills into each of
  `.claude/skills/`, `.agents/skills/`, and `plugins/synapse-a2a/skills/`.

## Command reference

| Command | Purpose |
|---|---|
| `gh skill install <owner>/<repo> <skill>` | Install a skill from a public repo. |
| `gh skill install <owner>/<repo> <skill> --pin <ref>` | Pin to a tag, branch, or SHA. |
| `gh skill install <owner>/<repo> <skill> --agent <name>` | Target a specific agent runtime. |
| `gh skill preview <owner>/<repo> <skill>` | Inspect a skill before installing. |
| `gh skill search <query>` | Find available skills. |
| `gh skill update` | Scan installed skills and apply upstream changes (pinned skills are skipped). |
| `gh skill publish` | Validate and publish skills in the current repo. Use `--fix` for metadata auto-repair. |

## Installing Synapse A2A skills

Replace the old `npx skills add s-hiraoku/synapse-a2a` command with:

```bash
# Core communication skill — auto-understands @agent messaging, priorities, File Safety
gh skill install s-hiraoku/synapse-a2a synapse-a2a

# Multi-agent orchestration skill
gh skill install s-hiraoku/synapse-a2a synapse-manager

# Re-inject instructions after /clear
gh skill install s-hiraoku/synapse-a2a synapse-reinst

# Pin to a release
gh skill install s-hiraoku/synapse-a2a synapse-a2a --pin v0.26.4

# Install for a specific agent
gh skill install s-hiraoku/synapse-a2a synapse-a2a --agent claude-code
gh skill install s-hiraoku/synapse-a2a synapse-a2a --agent copilot
```

Periodically run `gh skill update` to check for upstream changes.
Pinned skills are skipped — update them explicitly when you're ready
to move to a new release.

## Migration matrix

| Old command | New command |
|---|---|
| `npx skills add s-hiraoku/synapse-a2a` | `gh skill install s-hiraoku/synapse-a2a <skill-name>` (per skill) |
| `bash scripts/new_skill.sh <name>` | Author `SKILL.md` directly and run `gh skill publish` |
| `synapse skills add <repo>` (npx wrapper) | `gh skill install <repo> <skill>` |
| Ad-hoc `cp -r plugins/synapse-a2a/skills/... .claude/skills/` | `gh skill install s-hiraoku/synapse-a2a <skill> --agent claude-code` |
| "Update all skills" | `gh skill update` |

## Status of existing skill copies in this repo

The directories below currently contain committed copies of several
skills. They remain for backward compatibility while consumers
migrate:

- `plugins/synapse-a2a/skills/` — plugin distribution, still the
  authoritative source that `gh skill publish` reads from.
- `.claude/skills/` — committed copy for contributors running Claude
  Code directly on this repo's working tree.
- `.agents/skills/` — committed copy for Codex / OpenCode /
  Copilot / Gemini.

Do **not** delete these copies yet. They will be phased out on a
schedule communicated via the release notes once `gh skill install`
is confirmed as the primary consumer path.

## First-time publish (maintainer one-time setup)

Before any consumer can run `gh skill install s-hiraoku/synapse-a2a <skill>`,
this repository's maintainers must **publish** each skill so it is
discoverable by `gh skill`. Do this once per skill, per release:

```bash
# 1. Authenticate gh CLI to the repo
gh auth status                            # make sure you're logged in
gh auth refresh -s write:packages         # if publish reports scope issues

# 2. From the repo root, validate every skill under plugins/
for d in plugins/synapse-a2a/skills/*/; do
  echo "--- $(basename "$d") ---"
  (cd "$d" && gh skill publish --fix)     # --fix repairs frontmatter drift
done

# 3. Verify each skill is now discoverable
gh skill search synapse-a2a
gh skill preview s-hiraoku/synapse-a2a synapse-a2a

# 4. Tag the release so `--pin` targets are meaningful
git tag v0.26.2 && git push --tags
```

`gh skill publish` is idempotent per tree SHA — re-running on an
unchanged skill is a no-op. Publishing a new commit registers a new
tree SHA so that `gh skill update` clients see drift and can pull the
update. Pinned installs (`--pin v0.26.4`) continue to resolve against
the tagged ref you recorded at install time.

### CI automation (recommended)

Add a GitHub Actions step on every release that runs `gh skill publish`
for each skill in `plugins/synapse-a2a/skills/`. This keeps the
published registry in sync with the tag without relying on maintainer
laptops. The step needs a token with `write:packages` scope.

### Legacy publish path (still tolerated, not recommended)

The old `plugins/synapse-a2a/skills/anthropic-skill-creator/scripts/new_skill.sh`
helper still generates a usable skeleton, but:

- It does not register the skill with `gh skill`.
- It writes copies into `.claude/skills/` and `.agents/skills/`,
  which produce drift relative to `gh skill install` consumers.

Prefer authoring `SKILL.md` directly and running `gh skill publish`
from the skill directory.

## Publishing a new skill end-to-end

```bash
# 1. Create the skill directory
mkdir -p plugins/synapse-a2a/skills/my-new-skill

# 2. Author SKILL.md following agentskills.io spec
$EDITOR plugins/synapse-a2a/skills/my-new-skill/SKILL.md

# 3. Validate
(cd plugins/synapse-a2a/skills/my-new-skill && gh skill publish --fix)

# 4. Commit + tag
git add plugins/synapse-a2a/skills/my-new-skill
git commit -m "feat(skills): add my-new-skill"
git tag v0.27.1 && git push origin main --tags

# 5. Users can now install
#   gh skill install s-hiraoku/synapse-a2a my-new-skill --pin v0.27.1
```

## Troubleshooting

- **`unknown command "skill" for "gh"`** — `gh` CLI is below 2.90.0.
  Upgrade via your package manager (`nix`, `brew`, `scoop`, etc.).
- **`gh skill update` reports drift after a local `synapse workflow sync`**
  — expected: `synapse workflow sync` regenerates workflow-owned
  skill copies locally, which diverges from the published `gh skill`
  version. Decide which source of truth you want and re-publish or
  re-install accordingly.
- **Pinned skill stuck on an old version** — `gh skill install ... --pin <new-ref>`
  overwrites the pin. There is no "unpin" flag; re-install without
  `--pin` to move back to the moving target.

## Related

- [Skills](skills.md) — catalog of core skills, skill sets, and the
  `synapse skills` CLI for local skill management.
- [CLI Commands](../reference/cli.md) — full command reference,
  including `synapse skills` subcommands.
