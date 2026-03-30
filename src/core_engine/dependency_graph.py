"""
dependency_graph — Import-based module dependency graph builder.

Parses ``import`` and ``from … import`` statements from each module,
resolves them to file paths, and produces a directed acyclic (or cyclic)
graph of module dependencies.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core_engine.ast_parser import ParsedModule


@dataclass
class DependencyEdge:
    source: str  # file path of the importing module
    target: str  # file path of the imported module (or "<stdlib>", "<external>")
    import_name: str
    lineno: int


@dataclass
class DependencyGraph:
    nodes: set[str] = field(default_factory=set)  # file paths
    edges: list[DependencyEdge] = field(default_factory=list)
    adjacency: dict[str, list[str]] = field(default_factory=dict)
    cycles: list[list[str]] = field(default_factory=list)

    def add_node(self, node: str) -> None:
        self.nodes.add(node)

    def add_edge(self, edge: DependencyEdge) -> None:
        self.edges.append(edge)
        self.adjacency.setdefault(edge.source, []).append(edge.target)

    def successors(self, node: str) -> list[str]:
        return self.adjacency.get(node, [])

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": sorted(self.nodes),
            "edges": [
                {"source": e.source, "target": e.target, "import": e.import_name, "line": e.lineno}
                for e in self.edges
            ],
            "cycles": self.cycles,
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
        }


class DependencyGraphBuilder:
    """Constructs a module-level dependency graph from parsed modules."""

    def __init__(self, workspace_root: str | Path | None = None):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else None
        self._file_index: dict[str, str] = {}  # module_name → file_path

    def build(self, modules: list[ParsedModule]) -> DependencyGraph:
        graph = DependencyGraph()

        # Phase 1: Build a module name → file path index
        self._file_index.clear()
        for mod in modules:
            graph.add_node(mod.file_path)
            # Register by module name and also by relative stems
            self._file_index[mod.module_name] = mod.file_path
            if self.workspace_root:
                try:
                    rel = Path(mod.file_path).relative_to(self.workspace_root)
                    dotted = str(rel.with_suffix("")).replace(os.sep, ".").replace("/", ".")
                    self._file_index[dotted] = mod.file_path
                except ValueError:
                    pass

        # Phase 2: Resolve imports to file paths and create edges
        for mod in modules:
            for imp in mod.imports:
                target = self._resolve_import(imp.module or "", imp.names)
                if target and target != mod.file_path:
                    graph.add_edge(DependencyEdge(
                        source=mod.file_path,
                        target=target,
                        import_name=imp.module or imp.names[0],
                        lineno=imp.lineno,
                    ))

        # Phase 3: Detect cycles using Tarjan's algorithm
        graph.cycles = self._detect_cycles(graph)

        return graph

    def _resolve_import(self, module_name: str, names: list[str]) -> str | None:
        """Resolve a module name to a workspace file path."""
        # Direct lookup
        if module_name in self._file_index:
            return self._file_index[module_name]

        # Try each imported name
        for name in names:
            full = f"{module_name}.{name}" if module_name else name
            if full in self._file_index:
                return self._file_index[full]
            if name in self._file_index:
                return self._file_index[name]

        # Check if it's a standard library module
        if module_name and self._is_stdlib(module_name):
            return None  # Don't add stdlib edges

        return None

    @staticmethod
    def _is_stdlib(module_name: str) -> bool:
        top = module_name.split(".")[0]
        if top in sys.stdlib_module_names:
            return True
        try:
            __import__(top)
            return True
        except ImportError:
            return False

    @staticmethod
    def _detect_cycles(graph: DependencyGraph) -> list[list[str]]:
        """Tarjan's algorithm for strongly connected components."""
        index_counter = [0]
        stack: list[str] = []
        lowlink: dict[str, int] = {}
        index: dict[str, int] = {}
        on_stack: set[str] = set()
        sccs: list[list[str]] = []

        def strongconnect(v: str) -> None:
            index[v] = index_counter[0]
            lowlink[v] = index_counter[0]
            index_counter[0] += 1
            stack.append(v)
            on_stack.add(v)

            for w in graph.successors(v):
                if w not in index:
                    strongconnect(w)
                    lowlink[v] = min(lowlink[v], lowlink[w])
                elif w in on_stack:
                    lowlink[v] = min(lowlink[v], index[w])

            if lowlink[v] == index[v]:
                scc: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    scc.append(w)
                    if w == v:
                        break
                if len(scc) > 1:
                    sccs.append(scc)

        for node in graph.nodes:
            if node not in index:
                strongconnect(node)

        return sccs
