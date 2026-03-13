#!/usr/bin/env python3
"""Portable Markdown memory system CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

CURRENT_SCHEMA_VERSION = 1
ALLOWED_KINDS = {"context", "preference", "workflow", "decision", "session", "inbox"}
ALLOWED_SCOPES = {"base", "global", "project"}
ALLOWED_STATUSES = {"canonical", "draft", "raw"}
REQUIRED_NOTE_FIELDS = (
    "id",
    "title",
    "kind",
    "scope",
    "status",
    "priority",
    "audience",
    "updated_at",
    "tags",
    "summary",
)
REQUIRED_IGNORE_ENTRIES = (
    ".llm-memory/",
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".github/copilot-instructions.md",
    ".cursor/rules/llm-memory.mdc",
)


class MemoryError(Exception):
    """Base exception for memory CLI failures."""


class ValidationError(MemoryError):
    """Raised when a canonical note or manifest is invalid."""


@dataclass(frozen=True)
class Note:
    metadata: dict
    body: str
    path: Path
    layer: str

    @property
    def note_id(self) -> str:
        return str(self.metadata["id"])


@dataclass(frozen=True)
class AdapterSpec:
    name: str
    base_template: str
    output_path: str
    title: str


ADAPTERS = {
    "codex": AdapterSpec(
        name="codex",
        base_template="memory-system/adapters-src/codex/AGENTS.base.md",
        output_path="AGENTS.md",
        title="Codex Memory",
    ),
    "claude": AdapterSpec(
        name="claude",
        base_template="memory-system/adapters-src/claude/CLAUDE.base.md",
        output_path="CLAUDE.md",
        title="Claude Memory",
    ),
    "copilot": AdapterSpec(
        name="copilot",
        base_template="memory-system/adapters-src/copilot/copilot-instructions.base.md",
        output_path=".github/copilot-instructions.md",
        title="GitHub Copilot Memory",
    ),
    "cursor": AdapterSpec(
        name="cursor",
        base_template="memory-system/adapters-src/cursor/llm-memory.base.mdc",
        output_path=".cursor/rules/llm-memory.mdc",
        title="Cursor Memory",
    ),
    "gemini": AdapterSpec(
        name="gemini",
        base_template="memory-system/adapters-src/gemini/GEMINI.base.md",
        output_path="GEMINI.md",
        title="Gemini Memory",
    ),
}


def today_iso() -> str:
    return date.today().isoformat()


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "memory-system" / "tools" / "llm_memory.py").exists():
            return candidate
    raise MemoryError("Could not find repository root containing memory-system/tools/llm_memory.py")


def global_memory_root() -> Path:
    override = os.environ.get("LLM_MEMORY_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".llm-memory").resolve()


def project_memory_root(repo_root: Path) -> Path:
    return repo_root / ".llm-memory"


def generated_root(repo_root: Path) -> Path:
    return project_memory_root(repo_root) / ".generated"


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-") or "note"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def parse_scalar(value: str):
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        items = []
        for item in inner.split(","):
            cleaned = item.strip().strip("'").strip('"')
            if cleaned:
                items.append(cleaned)
        return items
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if (
        (value.startswith('"') and value.endswith('"'))
        or (value.startswith("'") and value.endswith("'"))
    ):
        return value[1:-1]
    return value


def parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        raise ValidationError("Missing YAML frontmatter opening delimiter")
    lines = text.splitlines()
    closing_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing_index = index
            break
    if closing_index is None:
        raise ValidationError("Missing YAML frontmatter closing delimiter")
    metadata = {}
    for raw_line in lines[1:closing_index]:
        line = raw_line.strip()
        if not line:
            continue
        if ":" not in line:
            raise ValidationError(f"Invalid frontmatter line: {raw_line}")
        key, value = raw_line.split(":", 1)
        metadata[key.strip()] = parse_scalar(value)
    body = "\n".join(lines[closing_index + 1 :]).strip()
    return metadata, body


def dump_frontmatter(metadata: dict) -> str:
    ordered_keys = list(REQUIRED_NOTE_FIELDS) + [
        key for key in metadata.keys() if key not in REQUIRED_NOTE_FIELDS
    ]
    lines = ["---"]
    for key in ordered_keys:
        if key not in metadata:
            continue
        value = metadata[key]
        if isinstance(value, list):
            rendered = ", ".join(str(item) for item in value)
            lines.append(f"{key}: [{rendered}]")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def render_note(metadata: dict, body: str) -> str:
    normalized_body = body.strip()
    if normalized_body:
        return f"{dump_frontmatter(metadata)}\n\n{normalized_body}\n"
    return f"{dump_frontmatter(metadata)}\n"


def ensure_note_metadata(metadata: dict, *, default_scope: str) -> dict:
    normalized = dict(metadata)
    normalized.setdefault("scope", default_scope)
    normalized.setdefault("status", "canonical")
    normalized.setdefault("priority", 50)
    normalized.setdefault("audience", ["all"])
    normalized.setdefault("tags", [])
    normalized.setdefault("updated_at", today_iso())
    normalized.setdefault("summary", "Pending summary.")
    if "title" in normalized and "id" not in normalized:
        normalized["id"] = slugify(str(normalized["title"]))
    return normalized


def validate_note_metadata(metadata: dict, *, path: Path, expected_scope: str | None = None) -> None:
    missing = [key for key in REQUIRED_NOTE_FIELDS if key not in metadata]
    if missing:
        raise ValidationError(f"{path}: missing required metadata fields: {', '.join(missing)}")
    if metadata["kind"] not in ALLOWED_KINDS:
        raise ValidationError(f"{path}: invalid kind '{metadata['kind']}'")
    if metadata["scope"] not in ALLOWED_SCOPES:
        raise ValidationError(f"{path}: invalid scope '{metadata['scope']}'")
    if metadata["status"] not in ALLOWED_STATUSES:
        raise ValidationError(f"{path}: invalid status '{metadata['status']}'")
    if expected_scope and metadata["scope"] != expected_scope:
        raise ValidationError(
            f"{path}: expected scope '{expected_scope}' but found '{metadata['scope']}'"
        )
    if not isinstance(metadata["priority"], int):
        raise ValidationError(f"{path}: priority must be an integer")
    if not isinstance(metadata["audience"], list):
        raise ValidationError(f"{path}: audience must be a list")
    if not isinstance(metadata["tags"], list):
        raise ValidationError(f"{path}: tags must be a list")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(metadata["updated_at"])):
        raise ValidationError(f"{path}: updated_at must be in YYYY-MM-DD format")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", str(metadata["id"])):
        raise ValidationError(f"{path}: id must use lowercase letters, digits, and hyphens")


def validate_manifest_data(data: dict, *, path: Path, expected_scope: str) -> None:
    required = {"schema_version", "scope", "created_by", "updated_at"}
    missing = sorted(required - set(data.keys()))
    if missing:
        raise ValidationError(f"{path}: missing manifest fields: {', '.join(missing)}")
    if data["scope"] != expected_scope:
        raise ValidationError(f"{path}: expected manifest scope '{expected_scope}'")
    if not isinstance(data["schema_version"], int) or data["schema_version"] < 1:
        raise ValidationError(f"{path}: schema_version must be a positive integer")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(data["updated_at"])):
        raise ValidationError(f"{path}: updated_at must be in YYYY-MM-DD format")


def load_note(path: Path, *, layer: str, expected_scope: str) -> Note:
    metadata, body = parse_frontmatter(read_text(path))
    metadata = ensure_note_metadata(metadata, default_scope=expected_scope)
    validate_note_metadata(metadata, path=path, expected_scope=expected_scope)
    return Note(metadata=metadata, body=body, path=path, layer=layer)


def load_notes_from_dir(root: Path, *, layer: str, expected_scope: str) -> list[Note]:
    notes: list[Note] = []
    if not root.exists():
        return notes
    for path in sorted(root.rglob("*.md")):
        if ".generated" in path.parts:
            continue
        notes.append(load_note(path, layer=layer, expected_scope=expected_scope))
    ids_seen: dict[str, Path] = {}
    for note in notes:
        existing = ids_seen.get(note.note_id)
        if existing:
            raise ValidationError(
                f"Duplicate note id '{note.note_id}' found in {existing} and {note.path}"
            )
        ids_seen[note.note_id] = note.path
    return notes


def load_manifest(root: Path, *, expected_scope: str) -> dict | None:
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        return None
    data = json.loads(read_text(manifest_path))
    validate_manifest_data(data, path=manifest_path, expected_scope=expected_scope)
    return data


def load_all_notes(repo_root: Path) -> tuple[list[Note], dict[str, dict]]:
    manifests: dict[str, dict] = {}
    all_notes: list[Note] = []
    base_root = repo_root / "memory-system" / "templates" / "base"
    all_notes.extend(load_notes_from_dir(base_root, layer="base", expected_scope="base"))

    global_root = global_memory_root()
    if global_root.exists():
        manifest = load_manifest(global_root, expected_scope="global")
        if manifest:
            manifests["global"] = manifest
        all_notes.extend(load_notes_from_dir(global_root, layer="global", expected_scope="global"))

    project_root = project_memory_root(repo_root)
    if project_root.exists():
        manifest = load_manifest(project_root, expected_scope="project")
        if manifest:
            manifests["project"] = manifest
        all_notes.extend(load_notes_from_dir(project_root, layer="project", expected_scope="project"))

    return all_notes, manifests


def note_sort_key(note: Note) -> tuple[int, int, str]:
    note_date = datetime.strptime(str(note.metadata["updated_at"]), "%Y-%m-%d").date()
    return (
        -int(note.metadata["priority"]),
        -note_date.toordinal(),
        str(note.metadata["title"]).lower(),
    )


def merge_notes(notes: Iterable[Note]) -> list[Note]:
    layer_order = {"base": 0, "global": 1, "project": 2}
    merged: dict[str, Note] = {}
    for note in sorted(notes, key=lambda item: (layer_order[item.layer], str(item.path))):
        merged[note.note_id] = note
    return sorted(merged.values(), key=note_sort_key)


def derive_summary(body: str) -> str:
    stripped = body.strip()
    if not stripped:
        return "Pending summary."
    first_line = stripped.splitlines()[0].strip("- ").strip()
    if len(first_line) > 120:
        return first_line[:117] + "..."
    return first_line or "Pending summary."


def copy_template_tree(src: Path, dest: Path) -> int:
    copied = 0
    for item in src.rglob("*"):
        relative = item.relative_to(src)
        target = dest / relative
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            copied += 1
    return copied


def ensure_manifest(root: Path, *, scope: str) -> bool:
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        data = json.loads(read_text(manifest_path))
        changed = False
    else:
        data = {"created_by": "llm_memory.py"}
        changed = True
    data["schema_version"] = CURRENT_SCHEMA_VERSION
    data["scope"] = scope
    data.setdefault("created_by", "llm_memory.py")
    data["updated_at"] = today_iso()
    validate_manifest_data(data, path=manifest_path, expected_scope=scope)
    write_text(manifest_path, json.dumps(data, indent=2) + "\n")
    return changed


def ensure_required_subdirs(root: Path) -> None:
    for name in ("decisions", "sessions", "inbox", ".generated"):
        (root / name).mkdir(parents=True, exist_ok=True)


def ensure_gitignore_entries(repo_root: Path) -> list[str]:
    gitignore = repo_root / ".gitignore"
    if not gitignore.exists():
        raise MemoryError(f"Missing required file: {gitignore}")
    lines = {line.strip() for line in read_text(gitignore).splitlines()}
    return [entry for entry in REQUIRED_IGNORE_ENTRIES if entry not in lines]


def capture_note(
    root: Path,
    *,
    scope: str,
    kind: str,
    title: str | None,
    text: str,
    tags: list[str],
) -> Path:
    ensure_manifest(root, scope=scope)
    ensure_required_subdirs(root)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    resolved_title = title or f"{kind.title()} Capture {timestamp}"
    note_id = f"{slugify(resolved_title)}-{timestamp.lower()}"
    metadata = {
        "id": note_id,
        "title": resolved_title,
        "kind": kind,
        "scope": scope,
        "status": "raw",
        "priority": 40,
        "audience": ["all"],
        "updated_at": today_iso(),
        "tags": tags,
        "summary": derive_summary(text),
    }
    note_path = root / "inbox" / f"{timestamp}-{slugify(resolved_title)}.md"
    write_text(note_path, render_note(metadata, text))
    return note_path


def target_directory_for_kind(root: Path, kind: str) -> Path:
    if kind == "decision":
        return root / "decisions"
    if kind == "session":
        return root / "sessions"
    return root


def update_summary_artifacts(root: Path, *, scope: str) -> None:
    if not root.exists():
        return
    ensure_required_subdirs(root)
    notes = load_notes_from_dir(root, layer=scope, expected_scope=scope)
    note_lines = ["# Note Index", ""]
    for note in sorted(notes, key=note_sort_key):
        relative = note.path.relative_to(root).as_posix()
        note_lines.append(
            f"- `{note.metadata['kind']}` `{note.metadata['status']}` "
            f"[{note.metadata['title']}]({relative})"
        )
    write_text(root / ".generated" / "note-index.md", "\n".join(note_lines).strip() + "\n")

    decision_lines = ["# Decision Summary", ""]
    decisions = [note for note in notes if note.metadata["kind"] == "decision"]
    if decisions:
        for note in decisions:
            decision_lines.append(f"- {note.metadata['updated_at']}: {note.metadata['summary']}")
    else:
        decision_lines.append("- No decision notes yet.")
    write_text(
        root / ".generated" / "decision-summary.md",
        "\n".join(decision_lines).strip() + "\n",
    )

    session_lines = ["# Session Summary", ""]
    sessions = [note for note in notes if note.metadata["kind"] == "session"]
    if sessions:
        for note in sorted(sessions, key=note_sort_key)[:10]:
            session_lines.append(f"- {note.metadata['updated_at']}: {note.metadata['summary']}")
    else:
        session_lines.append("- No session notes yet.")
    write_text(
        root / ".generated" / "session-summary.md",
        "\n".join(session_lines).strip() + "\n",
    )


def find_memory_root_for_path(source: Path) -> Path:
    current = source.resolve().parent
    for candidate in (current, *current.parents):
        if (candidate / "manifest.json").exists():
            return candidate
    raise MemoryError(f"Could not find memory root for {source}")


def promote_note(
    source: Path,
    *,
    default_scope: str,
    kind: str | None,
    title: str | None,
    note_id: str | None,
    summary: str | None,
    priority: int | None,
    keep_source: bool,
) -> Path:
    metadata, body = parse_frontmatter(read_text(source))
    metadata = ensure_note_metadata(metadata, default_scope=default_scope)
    promoted_kind = kind or (
        metadata["kind"]
        if metadata["kind"] in {"context", "preference", "workflow", "decision", "session"}
        else "context"
    )
    metadata["kind"] = promoted_kind
    metadata["status"] = "canonical"
    metadata["scope"] = default_scope
    metadata["title"] = title or metadata["title"]
    metadata["id"] = note_id or slugify(str(metadata["title"]))
    metadata["summary"] = summary or derive_summary(body)
    metadata["priority"] = priority if priority is not None else int(metadata.get("priority", 50))
    metadata["updated_at"] = today_iso()
    metadata.setdefault("audience", ["all"])
    metadata.setdefault("tags", [])

    root = find_memory_root_for_path(source)
    target_dir = target_directory_for_kind(root, promoted_kind)
    target_path = target_dir / f"{metadata['id']}.md"
    validate_note_metadata(metadata, path=target_path, expected_scope=default_scope)
    write_text(target_path, render_note(metadata, body))
    if not keep_source and source.resolve() != target_path.resolve():
        source.unlink()
    return target_path


def filter_stable_notes(notes: Iterable[Note]) -> list[Note]:
    return [
        note
        for note in notes
        if note.metadata["status"] == "canonical"
        and note.metadata["kind"] in {"context", "preference", "workflow", "decision"}
    ]


def recent_session_notes(notes: Iterable[Note]) -> list[Note]:
    cutoff = date.today() - timedelta(days=30)
    sessions = [
        note
        for note in notes
        if note.metadata["status"] == "canonical" and note.metadata["kind"] == "session"
    ]
    filtered = [
        note
        for note in sessions
        if datetime.strptime(str(note.metadata["updated_at"]), "%Y-%m-%d").date() >= cutoff
    ]
    filtered.sort(key=note_sort_key)
    return filtered[:10]


def render_compiled_sections(notes: list[Note]) -> str:
    stable = filter_stable_notes(notes)
    sessions = recent_session_notes(notes)

    lines = ["# Compiled Memory", ""]
    lines.append("## Stable Memory")
    lines.append("")
    if stable:
        for note in stable:
            lines.append(
                f"### {note.metadata['title']} "
                f"({note.metadata['kind']}, {note.metadata['scope']})"
            )
            lines.append(f"Summary: {note.metadata['summary']}")
            if note.metadata["tags"]:
                lines.append(f"Tags: {', '.join(note.metadata['tags'])}")
            if note.body:
                lines.append("")
                lines.extend(note.body.splitlines())
            lines.append("")
    else:
        lines.append("No stable memory has been promoted yet.")
        lines.append("")

    lines.append("## Recent Session Digest")
    lines.append("")
    if sessions:
        for note in sessions:
            lines.append(f"- {note.metadata['updated_at']} {note.metadata['title']}: {note.metadata['summary']}")
    else:
        lines.append("No recent canonical session notes.")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_adapter(repo_root: Path, adapter: AdapterSpec, compiled_sections: str) -> str:
    header = [
        "<!-- DO NOT EDIT; edit canonical memory and rebuild. -->",
        f"<!-- Adapter: {adapter.name} -->",
        "",
    ]
    base_template = read_text(repo_root / adapter.base_template).strip()
    return "\n".join(header + [base_template, "", compiled_sections.strip(), ""])


def build_outputs(repo_root: Path, adapter_names: list[str] | None = None) -> list[Path]:
    missing_entries = ensure_gitignore_entries(repo_root)
    if missing_entries:
        raise MemoryError(
            "Missing required .gitignore entries: " + ", ".join(missing_entries)
        )
    notes, _manifests = load_all_notes(repo_root)
    compiled_notes = merge_notes(notes)
    compiled_sections = render_compiled_sections(compiled_notes)

    gen_root = generated_root(repo_root)
    gen_root.mkdir(parents=True, exist_ok=True)
    write_text(gen_root / "compiled-context.md", compiled_sections)

    update_summary_artifacts(project_memory_root(repo_root), scope="project")
    if global_memory_root().exists():
        update_summary_artifacts(global_memory_root(), scope="global")

    adapters = [ADAPTERS[name] for name in (adapter_names or list(ADAPTERS.keys()))]
    written: list[Path] = []
    manifest = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "adapters": {},
        "compiled_hash": sha256_text(compiled_sections),
    }
    for adapter in adapters:
        output = repo_root / adapter.output_path
        rendered = render_adapter(repo_root, adapter, compiled_sections)
        write_text(output, rendered)
        written.append(output)
        manifest["adapters"][adapter.name] = {
            "path": adapter.output_path,
            "sha256": sha256_text(rendered),
        }
    write_text(gen_root / "build-manifest.json", json.dumps(manifest, indent=2) + "\n")
    return written


def scan_links(note: Note) -> list[str]:
    issues: list[str] = []
    for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", note.body):
        target = match.group(1)
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path_part = target.split("#", 1)[0]
        if not path_part:
            continue
        resolved = (note.path.parent / path_part).resolve()
        if not resolved.exists():
            issues.append(f"{note.path}: broken link target '{target}'")
    return issues


def validate_repo(repo_root: Path) -> list[str]:
    issues: list[str] = []
    missing_entries = ensure_gitignore_entries(repo_root)
    if missing_entries:
        issues.append("Missing required .gitignore entries: " + ", ".join(missing_entries))
    try:
        notes, manifests = load_all_notes(repo_root)
    except ValidationError as exc:
        issues.append(str(exc))
        return issues
    project_root = project_memory_root(repo_root)
    if project_root.exists() and "project" not in manifests:
        issues.append(f"Missing project manifest: {project_root / 'manifest.json'}")
    global_root = global_memory_root()
    if global_root.exists() and "global" not in manifests:
        issues.append(f"Missing global manifest: {global_root / 'manifest.json'}")
    for note in notes:
        issues.extend(scan_links(note))
    return issues


def tracked_paths(repo_root: Path, paths: list[str]) -> list[str]:
    if not (repo_root / ".git").exists():
        return []
    result = subprocess.run(
        ["git", "ls-files", "--", *paths],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 128):
        raise MemoryError(result.stderr.strip() or "git ls-files failed")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def doctor(repo_root: Path) -> list[str]:
    issues = validate_repo(repo_root)
    gen_manifest = generated_root(repo_root) / "build-manifest.json"
    if gen_manifest.exists():
        data = json.loads(read_text(gen_manifest))
        for _adapter_name, info in data.get("adapters", {}).items():
            output = repo_root / info["path"]
            if not output.exists():
                issues.append(f"Missing generated adapter output: {output}")
                continue
            actual_hash = sha256_text(read_text(output))
            if actual_hash != info["sha256"]:
                issues.append(f"Stale or manually edited adapter output detected: {output}")
    else:
        issues.append(f"Missing build manifest: {gen_manifest}")

    tracked = tracked_paths(
        repo_root,
        [
            ".llm-memory",
            "AGENTS.md",
            "CLAUDE.md",
            "GEMINI.md",
            ".github/copilot-instructions.md",
            ".cursor/rules/llm-memory.mdc",
        ],
    )
    if tracked:
        issues.append("Private memory or generated outputs are tracked by Git: " + ", ".join(tracked))
    return issues


def normalize_note_file(path: Path, *, scope: str) -> bool:
    metadata, body = parse_frontmatter(read_text(path))
    before = json.dumps(metadata, sort_keys=True)
    summary_missing = "summary" not in metadata or not str(metadata.get("summary", "")).strip()
    metadata = ensure_note_metadata(metadata, default_scope=scope)
    if summary_missing:
        metadata["summary"] = derive_summary(body)
    if metadata["kind"] not in ALLOWED_KINDS:
        metadata["kind"] = "context"
    if metadata["status"] not in ALLOWED_STATUSES:
        metadata["status"] = "canonical"
    if metadata["scope"] != scope:
        metadata["scope"] = scope
    validate_note_metadata(metadata, path=path, expected_scope=scope)
    after = json.dumps(metadata, sort_keys=True)
    if before != after:
        write_text(path, render_note(metadata, body))
        return True
    return False


def upgrade_memory_root(root: Path, *, scope: str) -> int:
    if not root.exists():
        return 0
    ensure_required_subdirs(root)
    ensure_manifest(root, scope=scope)
    changed = 0
    for path in sorted(root.rglob("*.md")):
        if ".generated" in path.parts:
            continue
        if normalize_note_file(path, scope=scope):
            changed += 1
    update_summary_artifacts(root, scope=scope)
    return changed


def command_init(args: argparse.Namespace) -> int:
    repo_root = find_repo_root()
    missing_entries = ensure_gitignore_entries(repo_root)
    if missing_entries:
        raise MemoryError("Missing required .gitignore entries: " + ", ".join(missing_entries))

    project_root = project_memory_root(repo_root)
    copied_project = copy_template_tree(
        repo_root / "memory-system" / "templates" / "project",
        project_root,
    )
    ensure_required_subdirs(project_root)
    ensure_manifest(project_root, scope="project")
    update_summary_artifacts(project_root, scope="project")
    print(f"Initialized project memory at {project_root} ({copied_project} files copied).")

    if args.init_global:
        global_root = global_memory_root()
        copied_global = copy_template_tree(
            repo_root / "memory-system" / "templates" / "global",
            global_root,
        )
        ensure_required_subdirs(global_root)
        ensure_manifest(global_root, scope="global")
        update_summary_artifacts(global_root, scope="global")
        print(f"Initialized global memory at {global_root} ({copied_global} files copied).")
    return 0


def command_capture(args: argparse.Namespace) -> int:
    repo_root = find_repo_root()
    root = global_memory_root() if args.scope == "global" else project_memory_root(repo_root)
    path = capture_note(
        root,
        scope=args.scope,
        kind=args.kind,
        title=args.title,
        text=" ".join(args.text).strip(),
        tags=args.tag or [],
    )
    update_summary_artifacts(root, scope=args.scope)
    print(f"Captured note at {path}")
    return 0


def command_promote(args: argparse.Namespace) -> int:
    repo_root = find_repo_root()
    promoted_paths: list[Path] = []
    for source_arg in args.sources:
        source = Path(source_arg)
        if not source.is_absolute():
            source = (Path.cwd() / source).resolve()
        if not source.exists():
            raise MemoryError(f"Source note does not exist: {source}")
        scope = args.scope
        if scope is None:
            scope = "global" if str(global_memory_root()) in str(source) else "project"
        promoted = promote_note(
            source,
            default_scope=scope,
            kind=args.kind,
            title=args.title,
            note_id=args.note_id,
            summary=args.summary,
            priority=args.priority,
            keep_source=args.keep_source,
        )
        promoted_paths.append(promoted)

    project_root = project_memory_root(repo_root)
    if project_root.exists():
        update_summary_artifacts(project_root, scope="project")
    if global_memory_root().exists():
        update_summary_artifacts(global_memory_root(), scope="global")

    for path in promoted_paths:
        print(f"Promoted note to {path}")
    return 0


def command_build(args: argparse.Namespace) -> int:
    repo_root = find_repo_root()
    written = build_outputs(repo_root, adapter_names=args.adapter)
    for path in written:
        print(f"Wrote {path}")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    repo_root = find_repo_root()
    issues = validate_repo(repo_root)
    if issues:
        for issue in issues:
            print(issue, file=sys.stderr)
        return 1
    print("Validation passed.")
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    repo_root = find_repo_root()
    issues = doctor(repo_root)
    if issues:
        for issue in issues:
            print(issue, file=sys.stderr)
        return 1
    print("Doctor checks passed.")
    return 0


def command_upgrade(args: argparse.Namespace) -> int:
    repo_root = find_repo_root()
    changed = 0
    changed += upgrade_memory_root(project_memory_root(repo_root), scope="project")
    changed += upgrade_memory_root(global_memory_root(), scope="global")
    print(f"Upgrade completed. Normalized {changed} note(s).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Portable Markdown memory system CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize project and optional global memory")
    init_parser.add_argument(
        "--global",
        dest="init_global",
        action="store_true",
        help="Initialize ~/.llm-memory as well",
    )
    init_parser.set_defaults(func=command_init)

    capture_parser = subparsers.add_parser("capture", help="Capture a raw note into inbox")
    capture_parser.add_argument("text", nargs="+", help="Raw note text")
    capture_parser.add_argument("--scope", choices=["project", "global"], default="project")
    capture_parser.add_argument("--kind", choices=["inbox", "session", "decision"], default="inbox")
    capture_parser.add_argument("--title")
    capture_parser.add_argument("--tag", action="append")
    capture_parser.set_defaults(func=command_capture)

    promote_parser = subparsers.add_parser("promote", help="Promote raw note(s) into canonical memory")
    promote_parser.add_argument("sources", nargs="+", help="Path(s) to inbox note files")
    promote_parser.add_argument("--scope", choices=["project", "global"])
    promote_parser.add_argument("--kind", choices=["context", "preference", "workflow", "decision", "session"])
    promote_parser.add_argument("--title")
    promote_parser.add_argument("--id", dest="note_id")
    promote_parser.add_argument("--summary")
    promote_parser.add_argument("--priority", type=int)
    promote_parser.add_argument("--keep-source", action="store_true")
    promote_parser.set_defaults(func=command_promote)

    build_parser_cmd = subparsers.add_parser("build", help="Build generated adapter outputs")
    build_parser_cmd.add_argument("--adapter", action="append", choices=sorted(ADAPTERS.keys()))
    build_parser_cmd.set_defaults(func=command_build)

    validate_parser = subparsers.add_parser("validate", help="Validate manifests and notes")
    validate_parser.set_defaults(func=command_validate)

    doctor_parser = subparsers.add_parser("doctor", help="Check ignore rules, drift, and tracked private files")
    doctor_parser.set_defaults(func=command_doctor)

    upgrade_parser = subparsers.add_parser("upgrade", help="Normalize local memory to the current schema")
    upgrade_parser.set_defaults(func=command_upgrade)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except MemoryError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
