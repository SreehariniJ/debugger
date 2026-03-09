from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any


class CodeScanner:
    def __init__(self, project_path: str, scan_cache_ttl_seconds: int = 5):
        self.project_path = Path(project_path).resolve()
        self.scan_cache_ttl_seconds = max(scan_cache_ttl_seconds, 0)
        self._scan_lock = threading.Lock()
        self._scan_cache: dict[tuple[str, ...], tuple[float, list[dict[str, Any]]]] = {}

    def get_context_for_file(self, target_file: str) -> str:
        """Read a file with UTF-8 fallback handling for robust cross-platform behavior."""
        try:
            return Path(target_file).read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return f"Error reading file: {exc}"

    def scan_workspace(self, root_dir: str | None = None) -> list[dict[str, Any]]:
        """Scan workspace for Python files while skipping noisy/untrusted directories."""
        root_path = Path(root_dir).resolve() if root_dir else self.project_path
        cache_key = (str(root_path),)

        if self.scan_cache_ttl_seconds > 0:
            with self._scan_lock:
                cached = self._scan_cache.get(cache_key)
                if cached and cached[0] > time.monotonic():
                    return [dict(item) for item in cached[1]]

        excluded_dirs = {
            ".git",
            "__pycache__",
            "venv",
            ".venv",
            "node_modules",
            ".pytest_cache",
            "frontend",
            "uploads",
            "dist",
            "build",
        }

        results: list[dict[str, Any]] = []
        stack = [root_path]

        while stack:
            current_dir = stack.pop()
            try:
                for entry in os.scandir(current_dir):
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name not in excluded_dirs:
                            stack.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False) and entry.name.endswith(".py"):
                        try:
                            stat = entry.stat()
                            file_path = Path(entry.path)
                            rel_path = file_path.relative_to(root_path)
                            results.append(
                                {
                                    "name": entry.name,
                                    "path": entry.path,
                                    "rel_path": str(rel_path),
                                    "size": stat.st_size,
                                    "mtime": stat.st_mtime,
                                }
                            )
                        except OSError:
                            continue
            except OSError:
                continue

        results.sort(key=lambda item: item["rel_path"])
        if self.scan_cache_ttl_seconds > 0:
            with self._scan_lock:
                self._scan_cache[cache_key] = (
                    time.monotonic() + self.scan_cache_ttl_seconds,
                    [dict(item) for item in results],
                )
        return results

    def invalidate_scan_cache(self) -> None:
        with self._scan_lock:
            self._scan_cache.clear()
