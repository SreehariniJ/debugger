"""
Tests for the Git-based safe patch system.

Covers:
  - Patch generation (unified diff output)
  - Patch application (hunk parsing + conflict detection)
  - API routes (generate, apply, preview)
  - Git workflow (mocked)

Note: Uses tempfile.mkdtemp() instead of pytest tmp_path to avoid
PermissionError on Windows with restricted temp directories.
"""

import os
import sys
import shutil
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch as mock_patch, MagicMock

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.patch_service import (
    generate_patch,
    generate_preview,
    apply_patch_to_content,
    _parse_unified_patch,
    _apply_hunks,
    apply_patch_smart,
    _apply_direct,
    PatchResult,
    PatchPreview,
    ApplyResult,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

BUGGY_CODE = (
    "def add(a, b):\n"
    "    return a - b  # BUG: should be +\n"
    "\n"
    "def greet(name):\n"
    "    print('Hello, ' + name)\n"
    "\n"
    "result = add(2, 3)\n"
    "print(result)\n"
)

FIXED_CODE = (
    "def add(a, b):\n"
    "    return a + b  # Fixed: addition\n"
    "\n"
    "def greet(name):\n"
    "    print('Hello, ' + name)\n"
    "\n"
    "result = add(2, 3)\n"
    "print(result)\n"
)


@pytest.fixture
def work_dir():
    """Create a writable temp directory for patch tests."""
    d = tempfile.mkdtemp(prefix="test_patch_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def temp_py_file(work_dir):
    """Create a temporary Python file with buggy code."""
    file_path = work_dir / "buggy.py"
    file_path.write_text(BUGGY_CODE, encoding="utf-8")
    return file_path


# ── Patch Generation Tests ─────────────────────────────────────────────────

class TestGeneratePatch:
    def test_basic_diff(self, temp_py_file):
        """Patch should contain the changed line."""
        result = generate_patch(temp_py_file, FIXED_CODE)

        assert isinstance(result, PatchResult)
        assert result.patch  # Non-empty
        assert "return a - b" in result.patch  # Deleted line
        assert "return a + b" in result.patch  # Added line
        assert result.additions >= 1
        assert result.deletions >= 1

    def test_no_changes(self, temp_py_file):
        """Identical code should produce an empty patch."""
        result = generate_patch(temp_py_file, BUGGY_CODE)

        assert result.patch == ""
        assert result.additions == 0
        assert result.deletions == 0

    def test_file_path_in_result(self, temp_py_file):
        """Result should contain the file path."""
        result = generate_patch(temp_py_file, FIXED_CODE)
        assert str(temp_py_file) in result.file_path

    def test_line_counts(self, temp_py_file):
        """Line counts should match the actual files."""
        result = generate_patch(temp_py_file, FIXED_CODE)
        assert result.original_lines == 8
        assert result.fixed_lines == 8

    def test_nonexistent_file(self, work_dir):
        """Should raise FileNotFoundError for nonexistent files."""
        fake_path = work_dir / "nonexistent.py"
        with pytest.raises(FileNotFoundError):
            generate_patch(fake_path, FIXED_CODE)

    def test_unified_diff_format(self, temp_py_file):
        """Patch should be in valid unified diff format."""
        result = generate_patch(temp_py_file, FIXED_CODE)
        lines = result.patch.splitlines()

        # First two lines should be --- and +++
        assert lines[0].startswith("---")
        assert lines[1].startswith("+++")

        # Should contain at least one @@ hunk header
        hunk_headers = [l for l in lines if l.startswith("@@")]
        assert len(hunk_headers) >= 1

    def test_additions_only(self, work_dir):
        """Adding new lines should only count additions."""
        original = "line1\nline2\n"
        fixed = "line1\nline_new\nline2\n"
        file_path = work_dir / "add_only.py"
        file_path.write_text(original, encoding="utf-8")

        result = generate_patch(file_path, fixed)
        assert result.additions >= 1

    def test_deletions_only(self, work_dir):
        """Removing lines should only count deletions."""
        original = "line1\nline_to_remove\nline2\n"
        fixed = "line1\nline2\n"
        file_path = work_dir / "del_only.py"
        file_path.write_text(original, encoding="utf-8")

        result = generate_patch(file_path, fixed)
        assert result.deletions >= 1


# ── Patch Preview Tests ─────────────────────────────────────────────────────

class TestGeneratePreview:
    def test_basic_preview(self, temp_py_file):
        """Preview should contain hunks with type info."""
        preview = generate_preview(temp_py_file, FIXED_CODE)

        assert isinstance(preview, PatchPreview)
        assert preview.hunks
        assert preview.original_code
        assert preview.fixed_code

        # Should have at least one non-equal hunk
        change_hunks = [h for h in preview.hunks if h["type"] != "equal"]
        assert len(change_hunks) >= 1

    def test_stats(self, temp_py_file):
        """Stats should include additions, deletions, modifications."""
        preview = generate_preview(temp_py_file, FIXED_CODE)

        assert "additions" in preview.stats
        assert "deletions" in preview.stats
        assert "modifications" in preview.stats
        assert "total_original_lines" in preview.stats

    def test_hunk_structure(self, temp_py_file):
        """Each hunk should have required fields."""
        preview = generate_preview(temp_py_file, FIXED_CODE)

        for hunk in preview.hunks:
            assert "type" in hunk
            assert hunk["type"] in ("equal", "replace", "insert", "delete")
            assert "original_start" in hunk
            assert "original_lines" in hunk
            assert "fixed_lines" in hunk


# ── Patch Application Tests ────────────────────────────────────────────────

class TestApplyPatch:
    def test_apply_clean_patch(self, temp_py_file):
        """A clean patch should apply without conflicts."""
        patch_result = generate_patch(temp_py_file, FIXED_CODE)
        original = temp_py_file.read_text(encoding="utf-8")

        patched, conflict = apply_patch_to_content(original, patch_result.patch)

        assert conflict is None
        assert "return a + b" in patched
        assert "return a - b" not in patched

    def test_empty_patch(self, temp_py_file):
        """Applying an empty patch should return original content unchanged."""
        original = temp_py_file.read_text(encoding="utf-8")
        patched, conflict = apply_patch_to_content(original, "")

        assert conflict is None
        assert patched == original

    def test_conflict_detection(self):
        """Should detect conflicts when patch doesn't match content."""
        original = "line1\nline2\nline3\n"

        patch_text = (
            "--- a/file.py\n"
            "+++ b/file.py\n"
            "@@ -1,3 +1,3 @@\n"
            " line1\n"
            "-wrong_line\n"
            "+new_line\n"
            " line3\n"
        )

        _, conflict = apply_patch_to_content(original, patch_text)
        assert conflict is not None
        assert "mismatch" in conflict.lower() or "conflict" in conflict.lower()

    def test_invalid_patch_format(self):
        """Should handle invalid patch format gracefully."""
        original = "some content\n"
        _, conflict = apply_patch_to_content(original, "not a valid patch")

        assert conflict is not None


# ── Hunk Parser Tests ───────────────────────────────────────────────────────

class TestHunkParser:
    def test_parse_single_hunk(self):
        """Should parse a single-hunk unified diff."""
        patch_text = (
            "--- a/file.py\n"
            "+++ b/file.py\n"
            "@@ -1,3 +1,3 @@\n"
            " line1\n"
            "-old_line\n"
            "+new_line\n"
            " line3\n"
        )
        hunks = _parse_unified_patch(patch_text)
        assert len(hunks) == 1
        assert hunks[0]["original_start"] == 1
        assert hunks[0]["original_count"] == 3

    def test_parse_multiple_hunks(self):
        """Should parse a multi-hunk unified diff."""
        patch_text = (
            "--- a/file.py\n"
            "+++ b/file.py\n"
            "@@ -1,3 +1,3 @@\n"
            " line1\n"
            "-old1\n"
            "+new1\n"
            " line3\n"
            "@@ -10,3 +10,3 @@\n"
            " line10\n"
            "-old2\n"
            "+new2\n"
            " line12\n"
        )
        hunks = _parse_unified_patch(patch_text)
        assert len(hunks) == 2
        assert hunks[0]["original_start"] == 1
        assert hunks[1]["original_start"] == 10


# ── Direct Apply (Fallback) Tests ──────────────────────────────────────────

class TestDirectApply:
    def test_direct_apply_creates_backup(self, temp_py_file):
        """Direct apply should create a .bak backup file."""
        result = _apply_direct(temp_py_file, FIXED_CODE)

        assert result.success
        assert result.method == "direct_patch"

        backup_path = temp_py_file.with_suffix(".py.bak")
        assert backup_path.exists()

        # Backup should contain original code
        backup_content = backup_path.read_text(encoding="utf-8")
        assert "return a - b" in backup_content

        # File should contain fixed code
        fixed_content = temp_py_file.read_text(encoding="utf-8")
        assert "return a + b" in fixed_content

    def test_direct_apply_nonexistent_file(self, work_dir):
        """Direct apply to a new file path should work."""
        new_path = work_dir / "new_file.py"
        result = _apply_direct(new_path, "print('hello')\n")

        assert result.success


# ── Smart Apply Tests ───────────────────────────────────────────────────────

class TestSmartApply:
    def test_smart_apply_no_git(self, temp_py_file):
        """Without Git, smart apply should fall back to direct patch."""
        with mock_patch("backend.services.patch_service.GIT_AVAILABLE", False):
            result = apply_patch_smart(
                temp_py_file,
                FIXED_CODE,
                use_git=True,
            )

        assert result.success
        assert result.method == "direct_patch"

    def test_smart_apply_git_disabled(self, temp_py_file):
        """With use_git=False, should skip Git even if available."""
        result = apply_patch_smart(
            temp_py_file,
            FIXED_CODE,
            use_git=False,
        )

        assert result.success
        assert result.method == "direct_patch"

    def test_smart_apply_with_patch_content(self, temp_py_file):
        """With patch_content and use_git=False, should apply via patch."""
        patch_result = generate_patch(temp_py_file, FIXED_CODE)

        with mock_patch("backend.services.patch_service.GIT_AVAILABLE", False):
            result = apply_patch_smart(
                temp_py_file,
                FIXED_CODE,
                patch_content=patch_result.patch,
                use_git=False,
            )

        assert result.success
        # Verify the file was actually patched
        content = temp_py_file.read_text(encoding="utf-8")
        assert "return a + b" in content


# ── Round-Trip Test ─────────────────────────────────────────────────────────

class TestRoundTrip:
    def test_generate_then_apply(self, temp_py_file):
        """Full round-trip: generate patch → apply patch → verify content."""
        # Generate
        patch_result = generate_patch(temp_py_file, FIXED_CODE)
        assert patch_result.patch

        # Read original
        original = temp_py_file.read_text(encoding="utf-8")

        # Apply
        patched, conflict = apply_patch_to_content(original, patch_result.patch)
        assert conflict is None

        # Verify
        assert "return a + b" in patched
        assert "return a - b" not in patched
        # Unchanged lines should remain
        assert "def greet(name):" in patched
        assert "result = add(2, 3)" in patched
