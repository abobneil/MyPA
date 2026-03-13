# Migrations

Schema migrations for ignored memory directories belong here.

Version `1` is the initial public schema. The current implementation performs
the v1 normalization inline in `llm_memory.py` and keeps this directory ready
for future explicit migration steps.
