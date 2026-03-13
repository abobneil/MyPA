---
name: llm-memory-manager
description: Manage the portable Markdown memory system in this repository. Use when Codex needs to initialize `.llm-memory`, capture raw notes, promote notes into canonical memory, rebuild generated adapter files, validate memory state, run schema upgrades, or avoid editing generated `AGENTS.md`, `CLAUDE.md`, Copilot, Cursor, or Gemini files directly.
---

# LLM Memory Manager

## Overview

Use the canonical Markdown memory files as the only editable source of truth.
Treat generated adapter files as read-only outputs produced by
`python memory-system/tools/llm_memory.py build`.

## Workflow

1. Read the current memory state before editing anything:
   - Project memory: `./.llm-memory/`
   - Optional global memory: `~/.llm-memory/` or `$LLM_MEMORY_HOME`
   - Generated state: `./.llm-memory/.generated/`
2. If local memory does not exist yet, run:
   - `python memory-system/tools/llm_memory.py init`
   - Add `--global` when the task should initialize cross-project memory too.
3. For new observations or unstable facts:
   - Capture them with `capture`.
   - Keep them raw until they are worth reusing.
4. For stable reusable information:
   - Promote the relevant note into canonical memory.
   - Choose the right `kind`: `context`, `preference`, `workflow`, `decision`, or `session`.
5. After canonical memory changes:
   - Run `validate`
   - Run `build`
   - Run `doctor`

## Rules

- Do not hand-edit generated adapter files.
- Do not store user-private memory in tracked repository files.
- Prefer short durable notes over long transcript dumps.
- Exclude raw inbox content from generated adapters until it is promoted.
- When choosing what to promote, prefer facts that are stable, reusable, and
  likely to matter across multiple tasks.

## Commands

- Initialize:
  - `python memory-system/tools/llm_memory.py init`
  - `python memory-system/tools/llm_memory.py init --global`
- Capture:
  - `python memory-system/tools/llm_memory.py capture --scope project --kind inbox "raw note"`
  - `python memory-system/tools/llm_memory.py capture --scope global --kind decision --title "API policy" "Prefer primary sources."`
- Promote:
  - `python memory-system/tools/llm_memory.py promote .llm-memory/inbox/<file>.md --kind workflow`
- Rebuild and verify:
  - `python memory-system/tools/llm_memory.py validate`
  - `python memory-system/tools/llm_memory.py build`
  - `python memory-system/tools/llm_memory.py doctor`
- Upgrade:
  - `python memory-system/tools/llm_memory.py upgrade`

## References

- Read `references/workflow.md` when you need the promotion heuristics, merge
  model, or adapter rebuild checklist.
