"""
core_engine — Whole-workspace program understanding subsystem.

Provides AST parsing, symbol resolution, dependency/call/control-flow
graph construction, and workspace indexing for the debugging platform.
"""

from core_engine.ast_parser import ASTParser
from core_engine.symbol_resolver import SymbolResolver
from core_engine.dependency_graph import DependencyGraphBuilder
from core_engine.call_graph import CallGraphBuilder
from core_engine.cfg_builder import CFGBuilder
from core_engine.workspace_indexer import WorkspaceIndexer

__all__ = [
    "ASTParser",
    "SymbolResolver",
    "DependencyGraphBuilder",
    "CallGraphBuilder",
    "CFGBuilder",
    "WorkspaceIndexer",
]
