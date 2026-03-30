"""
call_graph — Whole-workspace function-level call graph builder.

Constructs a directed graph where nodes are functions/methods and edges
represent call relationships.  Works by combining the ``CallSite`` list
from the AST parser with the ``SymbolTable`` from the symbol resolver.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core_engine.ast_parser import ParsedModule, CallSite
from core_engine.symbol_resolver import SymbolTable, SymbolResolver


@dataclass
class CallEdge:
    caller: str  # qualified name
    callee: str  # resolved qualified name
    lineno: int
    resolved: bool  # True if callee was resolved to a known definition


@dataclass
class CallGraph:
    nodes: set[str] = field(default_factory=set)
    edges: list[CallEdge] = field(default_factory=list)
    adjacency: dict[str, list[str]] = field(default_factory=dict)
    unresolved_calls: list[CallSite] = field(default_factory=list)

    def add_node(self, name: str) -> None:
        self.nodes.add(name)

    def add_edge(self, edge: CallEdge) -> None:
        self.edges.append(edge)
        self.adjacency.setdefault(edge.caller, []).append(edge.callee)

    def callees_of(self, func: str) -> list[str]:
        return self.adjacency.get(func, [])

    def callers_of(self, func: str) -> list[str]:
        return [e.caller for e in self.edges if e.callee == func]

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": sorted(self.nodes),
            "edges": [
                {"caller": e.caller, "callee": e.callee, "line": e.lineno, "resolved": e.resolved}
                for e in self.edges
            ],
            "unresolved": len(self.unresolved_calls),
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
        }


class CallGraphBuilder:
    """Builds a function-level call graph from parsed modules and symbol table."""

    def __init__(self, resolver: SymbolResolver | None = None):
        self.resolver = resolver or SymbolResolver()

    def build(self, modules: list[ParsedModule], symbol_table: SymbolTable) -> CallGraph:
        graph = CallGraph()

        # Register all known functions as nodes
        for mod in modules:
            prefix = mod.module_name
            for func in mod.functions:
                qname = f"{prefix}.{func.qualified_name}"
                graph.add_node(qname)
            for cls in mod.classes:
                for method in cls.methods:
                    qname = f"{prefix}.{method.qualified_name}"
                    graph.add_node(qname)

        # Resolve call sites to edges
        for mod in modules:
            prefix = mod.module_name
            for call in mod.calls:
                caller_qname = f"{prefix}.{call.caller}" if call.caller != "<module>" else f"{prefix}.<module>"
                graph.add_node(caller_qname)

                resolved = self.resolver.resolve_qualified_name(
                    call.callee_raw, prefix, symbol_table
                )

                if resolved and resolved.kind in ("function", "class"):
                    graph.add_edge(CallEdge(
                        caller=caller_qname,
                        callee=resolved.qualified_name,
                        lineno=call.lineno,
                        resolved=True,
                    ))
                else:
                    # Try simple name lookup
                    simple_defs = self.resolver.resolve_name(call.callee_raw, symbol_table)
                    func_defs = [d for d in simple_defs if d.kind in ("function", "class")]
                    if func_defs:
                        graph.add_edge(CallEdge(
                            caller=caller_qname,
                            callee=func_defs[0].qualified_name,
                            lineno=call.lineno,
                            resolved=True,
                        ))
                    else:
                        graph.add_edge(CallEdge(
                            caller=caller_qname,
                            callee=call.callee_raw,
                            lineno=call.lineno,
                            resolved=False,
                        ))
                        graph.unresolved_calls.append(call)

        return graph
