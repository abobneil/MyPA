# Upgrade Guide

## Goals

- Allow users to pull template improvements without losing local memory
- Keep the canonical memory schema versioned and migratable
- Keep upgrades idempotent

## Safe Upgrade Flow

1. Pull the latest tracked repository changes.
2. Run `python memory-system/tools/llm_memory.py upgrade`.
3. Run `python memory-system/tools/llm_memory.py validate`.
4. Run `python memory-system/tools/llm_memory.py build`.
5. Run `python memory-system/tools/llm_memory.py doctor`.

## What `upgrade` Does

- Ensures project and global manifests exist
- Backfills missing metadata on legacy notes
- Bumps manifest schema versions to the current supported version
- Leaves note bodies intact

## Git Behavior

Local memory lives in ignored paths:

- `./.llm-memory/`
- `~/.llm-memory/`

Generated adapter outputs are also ignored:

- `AGENTS.md`
- `CLAUDE.md`
- `GEMINI.md`
- `.github/copilot-instructions.md`
- `.cursor/rules/llm-memory.mdc`

If you want an extra local safeguard, add the same paths to `.git/info/exclude`.
