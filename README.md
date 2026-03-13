# Portable Markdown Memory System

This repository is a vendor-neutral template for keeping LLM memory in Markdown
and compiling it into tool-specific instruction files such as `AGENTS.md`,
`CLAUDE.md`, and `.github/copilot-instructions.md`.

## How The Memory Works

The system treats Markdown notes as the source of truth. You edit canonical
memory in `.llm-memory/` for this repository, and optionally in `~/.llm-memory/`
for personal memory shared across repositories. The generator then merges those
notes with the tracked base templates in `memory-system/templates/base/` and
renders adapter files for each supported tool.

Merge precedence is:

1. Base memory from `memory-system/templates/base/`
2. Global memory from `~/.llm-memory/`
3. Project memory from `./.llm-memory/`

If two notes share the same `id`, the later layer wins.

Each note has lightweight frontmatter that describes its role:

- `kind`: `context`, `preference`, `workflow`, `decision`, `session`, or `inbox`
- `scope`: `base`, `global`, or `project`
- `status`: `canonical`, `draft`, or `raw`

Build behavior is intentionally strict:

- Included in adapters: canonical `context`, `preference`, `workflow`, and
  `decision` notes
- Included as a digest: recent canonical `session` notes
- Excluded: raw inbox notes and draft notes

Generated adapter files are build artifacts. Do not edit `AGENTS.md`,
`CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`, or
`.cursor/rules/llm-memory.mdc` directly. Edit canonical memory and rebuild.

## Memory Layout

After initialization, the project memory folder looks like this:

```text
.llm-memory/
  00-index.md
  10-project-overview.md
  20-architecture.md
  30-workflows.md
  40-active-context.md
  decisions/
  inbox/
  sessions/
  .generated/
  manifest.json
```

What goes where:

- Root numbered files: durable high-value project memory
- `inbox/`: raw captures that have not been reviewed yet
- `decisions/`: canonical decision notes
- `sessions/`: canonical session notes
- `.generated/`: compiled context, summaries, and build metadata

## Typical Usage

### 1. Initialize Memory

```powershell
python memory-system/tools/llm_memory.py init --global
```

This creates project memory in `.llm-memory/` and, with `--global`, personal
memory in `~/.llm-memory/`.

### 2. Capture Or Edit Memory

For direct edits, update canonical notes in `.llm-memory/`.

For quick capture, write a raw note into `inbox/`:

```powershell
python memory-system/tools/llm_memory.py capture --title "Need repo setup docs" "User onboarding still needs setup steps."
```

When a raw note becomes worth keeping, promote it into canonical memory:

```powershell
python memory-system/tools/llm_memory.py promote .llm-memory/inbox/<note>.md --kind workflow --title "Developer Onboarding"
```

Promotion targets depend on note kind:

- `context`, `preference`, `workflow` -> `.llm-memory/`
- `decision` -> `.llm-memory/decisions/`
- `session` -> `.llm-memory/sessions/`

### 3. Rebuild Adapter Files

```powershell
python memory-system/tools/llm_memory.py build
```

You can also rebuild a single adapter:

```powershell
python memory-system/tools/llm_memory.py build --adapter codex
```

### 4. Validate And Check Health

```powershell
python memory-system/tools/llm_memory.py validate
python memory-system/tools/llm_memory.py doctor
```

Use `validate` to catch malformed notes and `doctor` to catch ignore-rule
problems, drift, and accidentally tracked private files.

## Recommended Workflow

Use this system as a note lifecycle:

1. Capture rough ideas in `inbox/` or `40-active-context.md`
2. Promote only stable, reusable information into canonical notes
3. Rebuild adapters after memory changes
4. Run `doctor` before committing changes

The rule of thumb is simple: keep temporary facts out of durable memory, and
keep durable memory out of generated adapter files.

## What This Repository Provides

- Base templates for project and global memory
- Generated adapters for Codex, Claude, GitHub Copilot, Cursor, and Gemini
- A Python CLI for init, capture, promote, build, validate, doctor, and upgrade
- Snapshot tests for adapter rendering

Private memory and generated adapter outputs are ignored by default and should
not be committed back to the public template repository.

Optional hardening:

- Copy [memory-system/hooks/pre-commit](/C:/Users/nchester/Documents/GitHub/MyPA/memory-system/hooks/pre-commit)
  to `.git/hooks/pre-commit` to block accidental commits of private memory and
  generated adapters.
