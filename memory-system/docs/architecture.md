# Architecture

## Overview

The memory system uses Markdown notes with small YAML-style frontmatter as the
source of truth. It compiles those notes into tool-specific instruction files
that are ignored by Git and can safely vary per clone.

Merge order:

1. Tracked base memory from `memory-system/templates/base/`
2. Optional global memory from `~/.llm-memory/`
3. Optional project memory from `./.llm-memory/`

Higher-precedence layers win when two notes share the same `id`.

## Directory Model

- `memory-system/templates/base/`
  - Tracked baseline notes shared by all users of the template repository
- `memory-system/templates/project/`
  - Files copied into `./.llm-memory/` during `init`
- `memory-system/templates/global/`
  - Files copied into `~/.llm-memory/` during `init --global`
- `memory-system/adapters-src/`
  - Tool-specific wrapper templates
- `./.llm-memory/.generated/`
  - Compiled context, hashes, and rendered adapter outputs used for drift checks

## Canonical Notes

Each note starts with frontmatter:

```yaml
---
id: project-overview
title: Project Overview
kind: context
scope: project
status: canonical
priority: 80
audience: [all]
updated_at: 2026-03-13
tags: [overview]
summary: Short one-line summary.
---
```

Supported `kind` values:

- `context`
- `preference`
- `workflow`
- `decision`
- `session`
- `inbox`

Supported `scope` values:

- `base`
- `global`
- `project`

Supported `status` values:

- `canonical`
- `draft`
- `raw`

## Adapter Policy

Generated adapters include:

- Canonical `context`, `preference`, `workflow`, and `decision` notes
- A bounded digest of recent session notes

Generated adapters exclude:

- Raw inbox notes
- Draft notes

The adapter outputs are generated artifacts and must not be edited by hand.
