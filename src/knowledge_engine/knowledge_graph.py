"""
knowledge_graph — Error → Cause → Fix knowledge graph.

Structures debugging knowledge as a directed graph where nodes are
error types, code patterns, and fix templates, connected by causal
relationships.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class KGNode:
    node_id: str
    node_type: str  # "error", "cause", "fix", "pattern"
    label: str
    description: str = ""
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class KGEdge:
    source: str  # node_id
    target: str  # node_id
    relation: str  # "caused_by", "fixed_by", "related_to", "symptom_of"
    weight: float = 1.0


class DebugKnowledgeGraph:
    """
    In-memory knowledge graph for debugging relationships.

    Supports traversal queries like:
        - "What causes ZeroDivisionError?"
        - "How is NameError fixed?"
        - "What errors are related to 'import' failures?"
    """

    def __init__(self) -> None:
        self._nodes: dict[str, KGNode] = {}
        self._edges: list[KGEdge] = []
        self._adjacency: dict[str, list[KGEdge]] = {}
        self._reverse_adjacency: dict[str, list[KGEdge]] = {}
        self._build_default_graph()

    def add_node(self, node: KGNode) -> None:
        self._nodes[node.node_id] = node

    def add_edge(self, edge: KGEdge) -> None:
        self._edges.append(edge)
        self._adjacency.setdefault(edge.source, []).append(edge)
        self._reverse_adjacency.setdefault(edge.target, []).append(edge)

    def get_node(self, node_id: str) -> KGNode | None:
        return self._nodes.get(node_id)

    def get_causes(self, error_id: str) -> list[KGNode]:
        """What causes this error?"""
        edges = self._adjacency.get(error_id, [])
        return [
            self._nodes[e.target]
            for e in edges
            if e.relation == "caused_by" and e.target in self._nodes
        ]

    def get_fixes(self, error_id: str) -> list[KGNode]:
        """What fixes this error?"""
        edges = self._adjacency.get(error_id, [])
        return [
            self._nodes[e.target]
            for e in edges
            if e.relation == "fixed_by" and e.target in self._nodes
        ]

    def get_related(self, node_id: str) -> list[KGNode]:
        """What is related to this node?"""
        forward = self._adjacency.get(node_id, [])
        backward = self._reverse_adjacency.get(node_id, [])
        related_ids = set()
        for e in forward:
            related_ids.add(e.target)
        for e in backward:
            related_ids.add(e.source)
        related_ids.discard(node_id)
        return [self._nodes[nid] for nid in related_ids if nid in self._nodes]

    def query_by_error(self, error_text: str) -> dict[str, Any]:
        """Find relevant knowledge for an error message."""
        error_lower = error_text.lower()
        matches: list[dict[str, Any]] = []

        for node in self._nodes.values():
            if node.node_type == "error":
                if node.node_id.lower() in error_lower or node.label.lower() in error_lower:
                    causes = self.get_causes(node.node_id)
                    fixes = self.get_fixes(node.node_id)
                    matches.append({
                        "error": node.label,
                        "description": node.description,
                        "causes": [{"label": c.label, "desc": c.description} for c in causes],
                        "fixes": [{"label": f.label, "desc": f.description} for f in fixes],
                    })

        return {
            "query": error_text,
            "matches": matches,
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [
                {"id": n.node_id, "type": n.node_type, "label": n.label}
                for n in self._nodes.values()
            ],
            "edges": [
                {"source": e.source, "target": e.target, "relation": e.relation}
                for e in self._edges
            ],
        }

    def _build_default_graph(self) -> None:
        """Populate with common Python debugging knowledge."""
        errors = [
            ("ZeroDivisionError", "Division or modulo by zero"),
            ("NameError", "Name is not defined in current scope"),
            ("TypeError", "Operation on incompatible types"),
            ("ValueError", "Correct type but inappropriate value"),
            ("IndexError", "Sequence index out of range"),
            ("KeyError", "Key not found in dictionary"),
            ("AttributeError", "Object has no such attribute"),
            ("ImportError", "Module could not be imported"),
            ("FileNotFoundError", "File or directory not found"),
            ("SyntaxError", "Invalid Python syntax"),
            ("IndentationError", "Incorrect indentation"),
            ("RecursionError", "Maximum recursion depth exceeded"),
            ("MemoryError", "Out of memory"),
            ("StopIteration", "Iterator has no more items"),
            ("RuntimeError", "Generic runtime error"),
        ]

        for name, desc in errors:
            self.add_node(KGNode(node_id=name, node_type="error", label=name, description=desc))

        # Causes
        cause_fix_map = {
            "ZeroDivisionError": [
                ("cause:unvalidated_denominator", "cause", "Denominator not checked before division"),
                ("fix:add_zero_check", "fix", "Add 'if denominator != 0' guard before division"),
            ],
            "NameError": [
                ("cause:typo_in_name", "cause", "Variable name misspelled"),
                ("cause:missing_import", "cause", "Required module not imported"),
                ("fix:correct_spelling", "fix", "Fix variable name spelling"),
                ("fix:add_import", "fix", "Add missing import statement"),
            ],
            "TypeError": [
                ("cause:wrong_arg_type", "cause", "Function called with wrong argument type"),
                ("cause:none_operation", "cause", "Operation performed on None value"),
                ("fix:add_type_check", "fix", "Add isinstance() check before operation"),
            ],
            "IndexError": [
                ("cause:off_by_one", "cause", "Loop boundary off by one"),
                ("cause:empty_sequence", "cause", "Accessing element of empty sequence"),
                ("fix:bounds_check", "fix", "Check len() before accessing index"),
            ],
            "KeyError": [
                ("cause:missing_key", "cause", "Dictionary accessed with non-existent key"),
                ("fix:use_get", "fix", "Use dict.get(key, default) instead of dict[key]"),
            ],
            "ImportError": [
                ("cause:missing_package", "cause", "Package not installed"),
                ("cause:circular_import", "cause", "Circular import dependency"),
                ("fix:install_package", "fix", "Install package with pip install"),
                ("fix:restructure_imports", "fix", "Move imports inside functions to break circular dependency"),
            ],
            "RecursionError": [
                ("cause:missing_base_case", "cause", "Recursive function lacks base case"),
                ("cause:incorrect_recursion", "cause", "Recursive call doesn't reduce problem size"),
                ("fix:add_base_case", "fix", "Add proper base case condition"),
            ],
        }

        for error_id, items in cause_fix_map.items():
            for item_id, item_type, description in items:
                self.add_node(KGNode(
                    node_id=item_id,
                    node_type=item_type,
                    label=item_id.split(":")[-1].replace("_", " ").title(),
                    description=description,
                ))
                relation = "caused_by" if item_type == "cause" else "fixed_by"
                self.add_edge(KGEdge(source=error_id, target=item_id, relation=relation))
