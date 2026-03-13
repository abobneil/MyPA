from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = Path("memory-system/tools/llm_memory.py")


def make_note(
    *,
    note_id: str,
    title: str,
    kind: str,
    scope: str,
    status: str,
    priority: int,
    summary: str,
    body: str,
    updated_at: str = "2026-03-13",
    tags: list[str] | None = None,
) -> str:
    rendered_tags = ", ".join(tags or [])
    return textwrap.dedent(
        f"""\
        ---
        id: {note_id}
        title: {title}
        kind: {kind}
        scope: {scope}
        status: {status}
        priority: {priority}
        audience: [all]
        updated_at: {updated_at}
        tags: [{rendered_tags}]
        summary: {summary}
        ---

        {body}
        """
    )


class MemoryCliTest(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_dir.name) / "repo"
        self.repo.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / ".gitignore", self.repo / ".gitignore")
        shutil.copy2(REPO_ROOT / "README.md", self.repo / "README.md")
        shutil.copytree(REPO_ROOT / "memory-system", self.repo / "memory-system")
        subprocess.run(["git", "init"], cwd=self.repo, check=True, capture_output=True, text=True)
        self.global_root = self.repo / ".test-global-memory"
        self.env = os.environ.copy()
        self.env["LLM_MEMORY_HOME"] = str(self.global_root)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_cli(self, *args: str, expect_ok: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *args],
            cwd=self.repo,
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )
        if expect_ok and result.returncode != 0:
            self.fail(f"Command failed: {' '.join(args)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
        if not expect_ok and result.returncode == 0:
            self.fail(f"Command unexpectedly passed: {' '.join(args)}\nSTDOUT:\n{result.stdout}")
        return result

    def write_repo_note(self, relative_path: str, content: str) -> None:
        target = self.repo / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")

    def test_init_creates_project_and_global_memory(self) -> None:
        self.run_cli("init", "--global")

        self.assertTrue((self.repo / ".llm-memory" / "manifest.json").exists())
        self.assertTrue((self.global_root / "manifest.json").exists())
        self.assertTrue((self.repo / ".llm-memory" / ".generated" / "note-index.md").exists())
        self.assertTrue((self.global_root / ".generated" / "note-index.md").exists())

    def test_default_build_matches_snapshots(self) -> None:
        self.run_cli("init")
        self.run_cli("build")

        snapshot_root = REPO_ROOT / "memory-system" / "tests" / "snapshots"
        targets = {
            "AGENTS.md": self.repo / "AGENTS.md",
            "CLAUDE.md": self.repo / "CLAUDE.md",
            "copilot-instructions.md": self.repo / ".github" / "copilot-instructions.md",
            "llm-memory.mdc": self.repo / ".cursor" / "rules" / "llm-memory.mdc",
            "GEMINI.md": self.repo / "GEMINI.md",
        }
        for snapshot_name, actual_path in targets.items():
            self.assertEqual(
                actual_path.read_text(encoding="utf-8"),
                (snapshot_root / snapshot_name).read_text(encoding="utf-8"),
            )

    def test_build_uses_merge_precedence_and_excludes_raw_notes(self) -> None:
        self.run_cli("init", "--global")
        self.write_repo_note(
            ".test-global-memory/team-style.md",
            make_note(
                note_id="team-style",
                title="Team Style",
                kind="preference",
                scope="global",
                status="canonical",
                priority=88,
                summary="Global preference that should be overridden.",
                body="Prefer the global style.",
                tags=["style"],
            ),
        )
        self.write_repo_note(
            ".llm-memory/team-style.md",
            make_note(
                note_id="team-style",
                title="Team Style",
                kind="preference",
                scope="project",
                status="canonical",
                priority=89,
                summary="Project-specific style override.",
                body="Prefer the project style.",
                tags=["style"],
            ),
        )
        self.run_cli("capture", "--title", "Raw Capture", "This raw note should never appear in adapters.")
        self.run_cli("build")

        agents = (self.repo / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Prefer the project style.", agents)
        self.assertNotIn("Prefer the global style.", agents)
        self.assertNotIn("This raw note should never appear in adapters.", agents)

    def test_promoted_session_appears_in_recent_digest(self) -> None:
        self.run_cli("init")
        self.run_cli(
            "capture",
            "--kind",
            "session",
            "--title",
            "Current Focus",
            "Investigate memory promotion flow for the next session.",
        )
        inbox_note = next((self.repo / ".llm-memory" / "inbox").glob("*.md"))
        self.run_cli("promote", str(inbox_note), "--kind", "session")
        self.run_cli("build")

        agents = (self.repo / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Recent Session Digest", agents)
        self.assertIn("Current Focus", agents)
        self.assertIn("Investigate memory promotion flow for the next session.", agents)

    def test_doctor_detects_manual_adapter_edits(self) -> None:
        self.run_cli("init")
        self.run_cli("build")
        with (self.repo / "AGENTS.md").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write("\nmanual edit\n")
        result = self.run_cli("doctor", expect_ok=False)
        self.assertIn("Stale or manually edited adapter output detected", result.stderr)

    def test_upgrade_normalizes_legacy_notes(self) -> None:
        legacy_root = self.repo / ".llm-memory"
        legacy_root.mkdir(parents=True, exist_ok=True)
        self.write_repo_note(
            ".llm-memory/legacy.md",
            textwrap.dedent(
                """\
                ---
                title: Legacy Note
                kind: context
                scope: project
                ---

                Legacy body content.
                """
            ),
        )
        self.run_cli("upgrade")
        self.run_cli("validate")

        upgraded = (self.repo / ".llm-memory" / "legacy.md").read_text(encoding="utf-8")
        self.assertIn("id: legacy-note", upgraded)
        self.assertIn("status: canonical", upgraded)
        self.assertIn("summary: Legacy body content.", upgraded)


if __name__ == "__main__":
    unittest.main()
