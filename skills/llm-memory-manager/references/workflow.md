# Workflow Reference

## Canonical Source Model

- Canonical memory lives in Markdown notes under `./.llm-memory/` and
  optionally `~/.llm-memory/`.
- Tool-facing files such as `AGENTS.md` and `CLAUDE.md` are generated outputs.
- Merge precedence is `base -> global -> project`, with later scopes winning by
  shared note `id`.

## Promotion Heuristics

Promote notes when the content is:

- Stable rather than task-specific
- Reusable across multiple sessions
- Important enough to shape future behavior
- Short enough to remain worth carrying as context

Keep notes raw in `inbox/` when the content is:

- Unverified
- Temporary
- Specific to a single task
- Better captured in source documents than in memory

## Adapter Rebuild Checklist

1. `python memory-system/tools/llm_memory.py validate`
2. `python memory-system/tools/llm_memory.py build`
3. `python memory-system/tools/llm_memory.py doctor`

If `doctor` reports drift, rebuild instead of patching the generated adapter
file directly.
