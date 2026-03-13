# Adapter Behavior

All adapters are rendered from the same compiled memory model. The generator
changes headings and wrapper text per tool, but the included memory content is
the same by default.

## Shared Behavior

- Adds a generated header warning against manual edits
- Includes stable canonical notes
- Includes a bounded recent session digest
- Excludes raw inbox notes
- Writes a hash manifest for drift detection

## Adapter Targets

- `AGENTS.md`
- `CLAUDE.md`
- `.github/copilot-instructions.md`
- `.cursor/rules/llm-memory.mdc`
- `GEMINI.md`

## Extension Model

To add a new adapter:

1. Add a base template under `memory-system/adapters-src/`.
2. Register the adapter in `llm_memory.py`.
3. Add a snapshot test.
