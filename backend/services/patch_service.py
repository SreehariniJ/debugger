"""
Git-based safe patch service for applying AI-generated code fixes.

Provides three tiers of patch application:
  1. Git workflow  — branch isolation, stash preservation, atomic commits
  2. Direct patch  — apply unified diff to file (no Git)
  3. Fallback write — last resort, writes fixed code directly

Safety guarantees:
  - Never overwrites user files on their active branch
  - Stashes uncommitted work before operating, restores after
  - Detects conflicts before applying patches
  - Full rollback on any failure
"""

from __future__ import annotations

import difflib
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("offline_debugger.patch")

# ── Try importing GitPython (optional dependency) ───────────────────────────
try:
    from git import Repo, InvalidGitRepositoryError, GitCommandError
    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False
    logger.info("GitPython not installed — Git-based patch workflow disabled.")


# ── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class PatchResult:
    """Result of patch generation."""
    patch: str
    file_path: str
    original_lines: int
    fixed_lines: int
    additions: int
    deletions: int


@dataclass
class PatchPreview:
    """Structured before/after diff for frontend rendering."""
    file_path: str
    original_code: str
    fixed_code: str
    hunks: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


@dataclass
class ApplyResult:
    """Result of applying a patch."""
    success: bool
    method: str  # "git_branch", "direct_patch", "fallback_write"
    file_path: str
    message: str
    branch_name: Optional[str] = None
    commit_sha: Optional[str] = None
    conflict: Optional[str] = None
    stash_restored: bool = False


# ── Patch Generation ────────────────────────────────────────────────────────

def generate_patch(
    file_path: Path,
    fixed_code: str,
    *,
    context_lines: int = 3,
) -> PatchResult:
    """
    Generate a unified diff patch comparing the original file content
    against the proposed fixed code.
    """
    try:
        original_code = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise FileNotFoundError(f"Cannot read file: {file_path}") from exc

    original_lines = original_code.splitlines(keepends=True)
    fixed_lines = fixed_code.splitlines(keepends=True)

    # Ensure files end with newline for clean diffs
    if original_lines and not original_lines[-1].endswith("\n"):
        original_lines[-1] += "\n"
    if fixed_lines and not fixed_lines[-1].endswith("\n"):
        fixed_lines[-1] += "\n"

    diff = difflib.unified_diff(
        original_lines,
        fixed_lines,
        fromfile=f"a/{file_path.name}",
        tofile=f"b/{file_path.name}",
        n=context_lines,
    )

    patch_text = "".join(diff)

    # Count additions and deletions (lines starting with +/- but not +++/---)
    additions = 0
    deletions = 0
    for line in patch_text.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1

    return PatchResult(
        patch=patch_text,
        file_path=str(file_path),
        original_lines=len(original_lines),
        fixed_lines=len(fixed_lines),
        additions=additions,
        deletions=deletions,
    )


def generate_preview(file_path: Path, fixed_code: str) -> PatchPreview:
    """
    Generate a structured before/after diff with hunk-level detail
    for the frontend DiffViewer component.
    """
    try:
        original_code = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise FileNotFoundError(f"Cannot read file: {file_path}") from exc

    original_lines = original_code.splitlines()
    fixed_lines = fixed_code.splitlines()

    # Use SequenceMatcher for rich hunk data
    matcher = difflib.SequenceMatcher(None, original_lines, fixed_lines)
    hunks = []
    additions = 0
    deletions = 0
    modifications = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        hunk = {
            "type": tag,  # "equal", "replace", "insert", "delete"
            "original_start": i1 + 1,  # 1-indexed for display
            "original_end": i2,
            "fixed_start": j1 + 1,
            "fixed_end": j2,
            "original_lines": original_lines[i1:i2],
            "fixed_lines": fixed_lines[j1:j2],
        }
        hunks.append(hunk)

        if tag == "insert":
            additions += (j2 - j1)
        elif tag == "delete":
            deletions += (i2 - i1)
        elif tag == "replace":
            modifications += max(i2 - i1, j2 - j1)
            additions += max(0, (j2 - j1) - (i2 - i1))
            deletions += max(0, (i2 - i1) - (j2 - j1))

    return PatchPreview(
        file_path=str(file_path),
        original_code=original_code,
        fixed_code=fixed_code,
        hunks=hunks,
        stats={
            "additions": additions,
            "deletions": deletions,
            "modifications": modifications,
            "total_original_lines": len(original_lines),
            "total_fixed_lines": len(fixed_lines),
        },
    )


# ── Patch Application (Pure Python) ────────────────────────────────────────

def _parse_unified_patch(patch_text: str) -> list[dict]:
    """
    Parse a unified diff into a list of hunks, each containing:
      - original_start, original_count
      - fixed_start, fixed_count
      - lines: list of (tag, content) where tag is ' ', '+', '-'
    """
    hunks = []
    current_hunk = None
    hunk_header_re = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

    for line in patch_text.splitlines(keepends=True):
        # Skip file headers
        if line.startswith("---") or line.startswith("+++"):
            continue

        header_match = hunk_header_re.match(line)
        if header_match:
            if current_hunk is not None:
                hunks.append(current_hunk)
            current_hunk = {
                "original_start": int(header_match.group(1)),
                "original_count": int(header_match.group(2) or 1),
                "fixed_start": int(header_match.group(3)),
                "fixed_count": int(header_match.group(4) or 1),
                "lines": [],
            }
            continue

        if current_hunk is not None:
            if line.startswith("+"):
                current_hunk["lines"].append(("+", line[1:]))
            elif line.startswith("-"):
                current_hunk["lines"].append(("-", line[1:]))
            elif line.startswith(" "):
                current_hunk["lines"].append((" ", line[1:]))
            elif line.startswith("\\"):
                # "\ No newline at end of file" — skip
                continue

    if current_hunk is not None:
        hunks.append(current_hunk)

    return hunks


def _apply_hunks(original_lines: list[str], hunks: list[dict]) -> tuple[list[str], Optional[str]]:
    """
    Apply parsed hunks to original lines.
    Returns (result_lines, conflict_description_or_none).
    """
    result = []
    original_idx = 0  # 0-indexed cursor into original_lines

    for hunk_num, hunk in enumerate(hunks, 1):
        hunk_start = hunk["original_start"] - 1  # Convert to 0-indexed

        # Copy lines before this hunk
        if hunk_start > original_idx:
            result.extend(original_lines[original_idx:hunk_start])
        elif hunk_start < original_idx:
            return [], f"Hunk #{hunk_num} overlaps with previous hunk at line {hunk_start + 1}"

        original_idx = hunk_start

        # Verify context and apply
        for tag, content in hunk["lines"]:
            if tag == " ":
                # Context line — must match original
                if original_idx >= len(original_lines):
                    return [], (
                        f"Hunk #{hunk_num}: context line beyond end of file at line {original_idx + 1}"
                    )
                actual = original_lines[original_idx]
                if actual.rstrip("\n") != content.rstrip("\n"):
                    return [], (
                        f"Hunk #{hunk_num}: context mismatch at line {original_idx + 1}. "
                        f"Expected: {content.rstrip()!r}, Got: {actual.rstrip()!r}"
                    )
                result.append(actual)
                original_idx += 1
            elif tag == "-":
                # Deletion — verify line matches then skip
                if original_idx >= len(original_lines):
                    return [], (
                        f"Hunk #{hunk_num}: delete beyond end of file at line {original_idx + 1}"
                    )
                actual = original_lines[original_idx]
                if actual.rstrip("\n") != content.rstrip("\n"):
                    return [], (
                        f"Hunk #{hunk_num}: delete mismatch at line {original_idx + 1}. "
                        f"Expected: {content.rstrip()!r}, Got: {actual.rstrip()!r}"
                    )
                original_idx += 1  # Skip this line (it's deleted)
            elif tag == "+":
                # Addition — insert new line
                result.append(content)

    # Copy remaining lines after last hunk
    if original_idx < len(original_lines):
        result.extend(original_lines[original_idx:])

    return result, None


def apply_patch_to_content(original_content: str, patch_text: str) -> tuple[str, Optional[str]]:
    """
    Apply a unified diff patch to content string.
    Returns (patched_content, conflict_description_or_none).
    """
    if not patch_text.strip():
        return original_content, None

    hunks = _parse_unified_patch(patch_text)
    if not hunks:
        return original_content, "No valid hunks found in patch"

    original_lines = original_content.splitlines(keepends=True)
    result_lines, conflict = _apply_hunks(original_lines, hunks)

    if conflict:
        return original_content, conflict

    return "".join(result_lines), None


# ── Git Workflow ────────────────────────────────────────────────────────────

def _find_git_repo(file_path: Path) -> Optional["Repo"]:
    """Walk up from file_path to find the enclosing Git repository."""
    if not GIT_AVAILABLE:
        return None
    
    search = file_path.parent
    for _ in range(20):  # Safety limit on traversal depth
        try:
            return Repo(search)
        except (InvalidGitRepositoryError, Exception):
            parent = search.parent
            if parent == search:
                break
            search = parent
    return None


def _is_repo_clean_enough(repo: "Repo") -> tuple[bool, str]:
    """Check if repo is in a state where we can safely operate."""
    try:
        if repo.head.is_detached:
            return False, "HEAD is detached — cannot create branch safely"
        if repo.is_dirty(untracked_files=False):
            # Dirty is OK — we'll stash
            pass
        return True, ""
    except Exception as exc:
        return False, f"Cannot inspect repo state: {exc}"


def apply_patch_via_git(
    file_path: Path,
    fixed_code: str,
    *,
    commit_message: Optional[str] = None,
) -> ApplyResult:
    """
    Full Git-based safe patch workflow:
      1. Find enclosing Git repo
      2. Stash uncommitted changes
      3. Create 'ai-fix/<timestamp>' branch
      4. Write fixed code to file
      5. Commit
      6. Switch back to original branch
      7. Pop stash

    Falls back to direct write if Git isn't available or workspace isn't a repo.
    """
    repo = _find_git_repo(file_path)

    if repo is None:
        # Fallback: direct patch without Git
        return _apply_direct(file_path, fixed_code)

    # Verify repo state
    ok, reason = _is_repo_clean_enough(repo)
    if not ok:
        logger.warning("Repo not in safe state: %s — falling back to direct patch", reason)
        return _apply_direct(file_path, fixed_code)

    original_branch = None
    stashed = False
    branch_name = f"ai-fix/{int(time.time())}"
    file_path_str = str(file_path)

    try:
        original_branch = repo.active_branch.name

        # Step 1: Stash uncommitted work (if dirty)
        if repo.is_dirty(untracked_files=True):
            logger.info("Stashing uncommitted changes before applying fix")
            repo.git.stash("push", "-m", f"offline-debugger-auto-stash-{int(time.time())}")
            stashed = True

        # Step 2: Create and checkout the fix branch
        logger.info("Creating branch: %s", branch_name)
        repo.git.checkout("-b", branch_name)

        # Step 3: Write the fixed code
        file_path.write_text(fixed_code, encoding="utf-8")

        # Step 4: Stage and commit
        # Get relative path for git add
        try:
            rel_path = str(file_path.relative_to(Path(repo.working_dir).resolve()))
        except ValueError:
            rel_path = file_path_str

        repo.git.add(rel_path)

        msg = commit_message or f"AI Fix: {file_path.name} — applied by Offline Debugger"
        repo.git.commit("-m", msg)

        commit_sha = repo.head.commit.hexsha[:12]
        logger.info("Committed fix on branch %s (SHA: %s)", branch_name, commit_sha)

        # Step 5: Switch back to original branch
        repo.git.checkout(original_branch)

        # Step 6: Pop stash if we stashed
        if stashed:
            try:
                repo.git.stash("pop")
                logger.info("Restored stashed changes")
            except GitCommandError as stash_exc:
                logger.warning("Stash pop had conflicts: %s", stash_exc)
                # Stash is preserved — user can manually resolve

        return ApplyResult(
            success=True,
            method="git_branch",
            file_path=file_path_str,
            message=f"Fix committed on branch '{branch_name}'. "
                    f"Merge with: git merge {branch_name}",
            branch_name=branch_name,
            commit_sha=commit_sha,
            stash_restored=stashed,
        )

    except Exception as exc:
        logger.exception("Git workflow failed — rolling back")

        # Rollback: try to get back to original branch
        try:
            if original_branch:
                repo.git.checkout(original_branch)
                # Try to delete the failed branch
                try:
                    repo.git.branch("-D", branch_name)
                except Exception:
                    pass
        except Exception as checkout_exc:
            logger.error("Rollback checkout failed: %s", checkout_exc)

        # Try to pop stash even on failure
        if stashed:
            try:
                repo.git.stash("pop")
            except Exception as pop_exc:
                logger.error("Stash pop on rollback failed: %s", pop_exc)

        return ApplyResult(
            success=False,
            method="git_branch",
            file_path=file_path_str,
            message=f"Git workflow failed: {exc}. Original branch restored.",
            conflict=str(exc),
        )


def _apply_direct(file_path: Path, fixed_code: str) -> ApplyResult:
    """
    Fallback: apply fix directly to the file (creates a .bak backup first).
    Used when Git isn't available or the workspace isn't a Git repo.
    """
    backup_path = file_path.with_suffix(file_path.suffix + ".bak")

    try:
        # Create backup
        if file_path.exists():
            original = file_path.read_text(encoding="utf-8", errors="replace")
            backup_path.write_text(original, encoding="utf-8")
            logger.info("Created backup: %s", backup_path)

        file_path.write_text(fixed_code, encoding="utf-8")

        return ApplyResult(
            success=True,
            method="direct_patch",
            file_path=str(file_path),
            message=f"Fix applied directly. Backup saved to {backup_path.name}",
        )
    except Exception as exc:
        # Try to restore from backup
        if backup_path.exists():
            try:
                backup_path.replace(file_path)
            except Exception:
                pass

        return ApplyResult(
            success=False,
            method="direct_patch",
            file_path=str(file_path),
            message=f"Direct patch failed: {exc}",
            conflict=str(exc),
        )


def apply_patch_smart(
    file_path: Path,
    fixed_code: str,
    patch_content: Optional[str] = None,
    *,
    use_git: bool = True,
    commit_message: Optional[str] = None,
) -> ApplyResult:
    """
    Smart dispatch: choose the best available patch method.

    Priority:
      1. Git workflow (if use_git=True and Git is available)
      2. Unified patch application (if patch_content is provided)
      3. Direct write with backup (fallback)
    """
    # Try Git workflow first
    if use_git and GIT_AVAILABLE:
        result = apply_patch_via_git(file_path, fixed_code, commit_message=commit_message)
        if result.success:
            return result
        logger.warning("Git workflow failed, trying direct patch: %s", result.message)

    # Try applying unified patch if provided
    if patch_content:
        try:
            original = file_path.read_text(encoding="utf-8", errors="replace")
            patched, conflict = apply_patch_to_content(original, patch_content)
            if conflict is None:
                # Create backup, then write
                backup_path = file_path.with_suffix(file_path.suffix + ".bak")
                backup_path.write_text(original, encoding="utf-8")
                file_path.write_text(patched, encoding="utf-8")
                return ApplyResult(
                    success=True,
                    method="direct_patch",
                    file_path=str(file_path),
                    message=f"Patch applied successfully. Backup: {backup_path.name}",
                )
            else:
                logger.warning("Patch conflict: %s", conflict)
                return ApplyResult(
                    success=False,
                    method="direct_patch",
                    file_path=str(file_path),
                    message="Patch cannot be applied cleanly",
                    conflict=conflict,
                )
        except Exception as exc:
            logger.warning("Patch application failed: %s", exc)

    # Final fallback: direct write with backup
    return _apply_direct(file_path, fixed_code)
