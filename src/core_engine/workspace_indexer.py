"""
workspace_indexer — High-level orchestrator for the core_engine.

Scans a workspace, parses all Python files, builds symbol tables and
graphs, and provides a unified ``ProjectIndex`` for consumption by all
other subsystems (agents, analysis engines, visualization).
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core_engine.ast_parser import ASTParser, ParsedModule
from core_engine.symbol_resolver import SymbolResolver, SymbolTable
from core_engine.dependency_graph import DependencyGraphBuilder, DependencyGraph
from core_engine.call_graph import CallGraphBuilder, CallGraph
from core_engine.cfg_builder import CFGBuilder, ControlFlowGraph


@dataclass
class ProjectIndex:
    """Unified workspace model consumed by all subsystems."""
    workspace_root: str
    modules: list[ParsedModule] = field(default_factory=list)
    symbol_table: SymbolTable | None = None
    dependency_graph: DependencyGraph | None = None
    call_graph: CallGraph | None = None
    cfgs: dict[str, list[ControlFlowGraph]] = field(default_factory=dict)
    build_time_seconds: float = 0.0
    indexed_at: float = 0.0

    @property
    def total_files(self) -> int:
        return len(self.modules)

    @property
    def total_functions(self) -> int:
        return sum(len(m.functions) for m in self.modules)

    @property
    def total_classes(self) -> int:
        return sum(len(m.classes) for m in self.modules)

    @property
    def total_loc(self) -> int:
        return sum(m.loc for m in self.modules)

    @property
    def total_sloc(self) -> int:
        return sum(m.sloc for m in self.modules)

    def summary(self) -> dict[str, Any]:
        return {
            "workspace_root": self.workspace_root,
            "total_files": self.total_files,
            "total_functions": self.total_functions,
            "total_classes": self.total_classes,
            "total_loc": self.total_loc,
            "total_sloc": self.total_sloc,
            "dependency_cycles": len(self.dependency_graph.cycles) if self.dependency_graph else 0,
            "call_graph_nodes": len(self.call_graph.nodes) if self.call_graph else 0,
            "call_graph_edges": len(self.call_graph.edges) if self.call_graph else 0,
            "unresolved_calls": len(self.call_graph.unresolved_calls) if self.call_graph else 0,
            "cfg_count": sum(len(v) for v in self.cfgs.values()),
            "build_time_seconds": round(self.build_time_seconds, 3),
            "indexed_at": self.indexed_at,
        }


class WorkspaceIndexer:
    """Scans a Python workspace and builds a complete ``ProjectIndex``."""

    EXCLUDED_DIRS = {
        ".git", "__pycache__", "venv", ".venv", "node_modules",
        ".pytest_cache", "frontend", "uploads", "dist", "build",
        ".gemini", ".antigravity", ".vscode", ".idea", ".tox",
        ".mypy_cache", ".ruff_cache", "eggs", ".eggs",
    }

    def __init__(
        self,
        workspace_root: str | Path,
        build_cfgs: bool = True,
        max_files: int = 500,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.build_cfgs_flag = build_cfgs
        self.max_files = max_files
        self._parser = ASTParser()
        self._resolver = SymbolResolver()
        self._lock = threading.Lock()
        self._cache: ProjectIndex | None = None
        self._cache_time: float = 0.0
        self._cache_ttl: float = 10.0  # seconds

    def index(self, force_refresh: bool = False) -> ProjectIndex:
        """Build or return cached project index."""
        now = time.monotonic()
        with self._lock:
            if (
                not force_refresh
                and self._cache is not None
                and (now - self._cache_time) < self._cache_ttl
            ):
                return self._cache

        idx = self._build_index()
        with self._lock:
            self._cache = idx
            self._cache_time = time.monotonic()
        return idx

    def invalidate(self) -> None:
        with self._lock:
            self._cache = None
            self._cache_time = 0.0

    def _build_index(self) -> ProjectIndex:
        start = time.monotonic()

        # Phase 1: Discover Python files
        py_files = self._discover_files()

        # Phase 2: Parse all files
        modules: list[ParsedModule] = []
        for fp in py_files[:self.max_files]:
            modules.append(self._parser.parse_file(fp))

        # Phase 3: Build symbol table
        symbol_table = self._resolver.build_symbol_table(modules)

        # Phase 4: Build dependency graph
        dep_builder = DependencyGraphBuilder(self.workspace_root)
        dep_graph = dep_builder.build(modules)

        # Phase 5: Build call graph
        call_builder = CallGraphBuilder(self._resolver)
        call_graph = call_builder.build(modules, symbol_table)

        # Phase 6: Build CFGs (optional, can be slow for large workspaces)
        cfgs: dict[str, list[ControlFlowGraph]] = {}
        if self.build_cfgs_flag:
            cfg_builder = CFGBuilder()
            for mod in modules:
                if mod.errors:
                    continue
                try:
                    source = Path(mod.file_path).read_text(encoding="utf-8", errors="replace")
                    func_cfgs = cfg_builder.build_for_source(source)
                    if func_cfgs:
                        cfgs[mod.file_path] = func_cfgs
                except OSError:
                    continue

        elapsed = time.monotonic() - start

        return ProjectIndex(
            workspace_root=str(self.workspace_root),
            modules=modules,
            symbol_table=symbol_table,
            dependency_graph=dep_graph,
            call_graph=call_graph,
            cfgs=cfgs,
            build_time_seconds=elapsed,
            indexed_at=time.time(),
        )

    def _discover_files(self) -> list[str]:
        """Walk workspace and collect .py file paths."""
        results: list[str] = []
        for root, dirs, files in os.walk(self.workspace_root, topdown=True):
            dirs[:] = [d for d in dirs if d not in self.EXCLUDED_DIRS]
            for fname in files:
                if fname.endswith(".py"):
                    results.append(os.path.join(root, fname))
                    if len(results) >= self.max_files:
                        return results
        results.sort()
        return results
