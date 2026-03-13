# Portable Markdown Memory System

This repository is a vendor-neutral template for maintaining private, local LLM
memory in Markdown and compiling it into tool-specific instruction files.

## What It Provides

- Canonical Markdown memory files stored in `.llm-memory/` and optionally
  `~/.llm-memory/`
- Generated adapter outputs for Codex, Claude, GitHub Copilot, Cursor, and
  Gemini
- A Python CLI for initialization, capture, promotion, build, validation,
  health checks, and upgrades
- A thin optional Codex skill for managing the system from inside Codex

## Quick Start

```powershell
python memory-system/tools/llm_memory.py init --global
python memory-system/tools/llm_memory.py build
python memory-system/tools/llm_memory.py doctor
```

Private memory and generated adapter outputs are ignored by default and should
not be committed back to the public template repository.

Optional hardening:

- Copy [memory-system/hooks/pre-commit](/C:/Users/nchester/Documents/GitHub/MyPA/memory-system/hooks/pre-commit)
  to `.git/hooks/pre-commit` to block accidental commits of private memory and
  generated adapters.
