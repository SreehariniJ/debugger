"""
cfg_builder — Control Flow Graph (CFG) construction from Python AST.

Builds a basic-block–level control flow graph for individual functions.
Each basic block is a linear sequence of statements; edges represent
branching decisions (if/else, loops, try/except, return).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BasicBlock:
    block_id: int
    statements: list[tuple[int, str]] = field(default_factory=list)  # (lineno, type)
    label: str = ""

    def add_statement(self, lineno: int, stmt_type: str) -> None:
        self.statements.append((lineno, stmt_type))

    @property
    def start_line(self) -> int | None:
        return self.statements[0][0] if self.statements else None

    @property
    def end_line(self) -> int | None:
        return self.statements[-1][0] if self.statements else None


@dataclass
class CFGEdge:
    source: int  # block_id
    target: int  # block_id
    label: str = ""  # "true", "false", "except", "finally", "loop_back", ""


@dataclass
class ControlFlowGraph:
    function_name: str
    blocks: dict[int, BasicBlock] = field(default_factory=dict)
    edges: list[CFGEdge] = field(default_factory=list)
    entry_block: int = 0
    exit_block: int = -1

    def add_block(self, block: BasicBlock) -> None:
        self.blocks[block.block_id] = block

    def add_edge(self, source: int, target: int, label: str = "") -> None:
        self.edges.append(CFGEdge(source=source, target=target, label=label))

    def successors(self, block_id: int) -> list[int]:
        return [e.target for e in self.edges if e.source == block_id]

    def predecessors(self, block_id: int) -> list[int]:
        return [e.source for e in self.edges if e.target == block_id]

    def to_dict(self) -> dict[str, Any]:
        return {
            "function": self.function_name,
            "blocks": {
                bid: {
                    "id": bid,
                    "label": b.label,
                    "statements": b.statements,
                    "start_line": b.start_line,
                    "end_line": b.end_line,
                }
                for bid, b in self.blocks.items()
            },
            "edges": [
                {"source": e.source, "target": e.target, "label": e.label}
                for e in self.edges
            ],
            "entry": self.entry_block,
            "exit": self.exit_block,
        }


class CFGBuilder:
    """Builds control flow graphs for Python functions from their ASTs."""

    def __init__(self) -> None:
        self._block_counter = 0

    def build_for_function(self, func_source: str, func_name: str = "<function>") -> ControlFlowGraph:
        """Build a CFG from a function's source code."""
        try:
            tree = ast.parse(func_source)
        except SyntaxError:
            cfg = ControlFlowGraph(function_name=func_name)
            err_block = self._new_block("syntax_error")
            cfg.add_block(err_block)
            cfg.entry_block = err_block.block_id
            cfg.exit_block = err_block.block_id
            return cfg

        # Find the first function definition
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return self._build_from_node(node)

        # Fallback: treat the whole module as a single block
        return self._build_from_module(tree, func_name)

    def build_for_source(self, source: str) -> list[ControlFlowGraph]:
        """Build CFGs for all functions in a source string."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        cfgs: list[ControlFlowGraph] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cfgs.append(self._build_from_node(node))
        return cfgs

    def _build_from_node(self, func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> ControlFlowGraph:
        self._block_counter = 0
        cfg = ControlFlowGraph(function_name=func_node.name)

        entry = self._new_block("entry")
        exit_block = self._new_block("exit")
        cfg.add_block(entry)
        cfg.add_block(exit_block)
        cfg.entry_block = entry.block_id
        cfg.exit_block = exit_block.block_id

        last_blocks = self._process_body(func_node.body, entry, exit_block, cfg)
        for lb in last_blocks:
            if lb != exit_block.block_id:
                cfg.add_edge(lb, exit_block.block_id, "fall-through")

        return cfg

    def _build_from_module(self, tree: ast.Module, name: str) -> ControlFlowGraph:
        self._block_counter = 0
        cfg = ControlFlowGraph(function_name=name)

        entry = self._new_block("entry")
        exit_block = self._new_block("exit")
        cfg.add_block(entry)
        cfg.add_block(exit_block)
        cfg.entry_block = entry.block_id
        cfg.exit_block = exit_block.block_id

        last_blocks = self._process_body(tree.body, entry, exit_block, cfg)
        for lb in last_blocks:
            if lb != exit_block.block_id:
                cfg.add_edge(lb, exit_block.block_id, "fall-through")

        return cfg

    def _process_body(
        self,
        stmts: list[ast.stmt],
        current_block: BasicBlock,
        exit_block: BasicBlock,
        cfg: ControlFlowGraph,
    ) -> list[int]:
        """Process a list of statements, returning the IDs of the 'last' blocks."""
        active_block = current_block
        last_blocks: list[int] = []

        for stmt in stmts:
            if isinstance(stmt, ast.If):
                result_blocks = self._handle_if(stmt, active_block, exit_block, cfg)
                if not result_blocks:
                    return last_blocks
                merge = self._new_block("merge")
                cfg.add_block(merge)
                for rb in result_blocks:
                    cfg.add_edge(rb, merge.block_id, "merge")
                active_block = merge

            elif isinstance(stmt, (ast.For, ast.While, ast.AsyncFor)):
                result_blocks = self._handle_loop(stmt, active_block, exit_block, cfg)
                if not result_blocks:
                    return last_blocks
                merge = self._new_block("after_loop")
                cfg.add_block(merge)
                for rb in result_blocks:
                    cfg.add_edge(rb, merge.block_id, "merge")
                active_block = merge

            elif isinstance(stmt, ast.Try):
                result_blocks = self._handle_try(stmt, active_block, exit_block, cfg)
                if not result_blocks:
                    return last_blocks
                merge = self._new_block("after_try")
                cfg.add_block(merge)
                for rb in result_blocks:
                    cfg.add_edge(rb, merge.block_id, "merge")
                active_block = merge

            elif isinstance(stmt, ast.Return):
                active_block.add_statement(stmt.lineno, "Return")
                cfg.add_edge(active_block.block_id, exit_block.block_id, "return")
                return last_blocks  # no further statements reachable

            elif isinstance(stmt, (ast.Raise, ast.Assert)):
                active_block.add_statement(stmt.lineno, type(stmt).__name__)
                # These may or may not terminate; add as possible exit
                last_blocks.append(active_block.block_id)
                new_block = self._new_block("post_raise")
                cfg.add_block(new_block)
                cfg.add_edge(active_block.block_id, new_block.block_id, "fall-through")
                active_block = new_block

            else:
                active_block.add_statement(stmt.lineno, type(stmt).__name__)

        last_blocks.append(active_block.block_id)
        return last_blocks

    def _handle_if(
        self, node: ast.If, block: BasicBlock, exit_block: BasicBlock, cfg: ControlFlowGraph
    ) -> list[int]:
        block.add_statement(node.lineno, "If")

        true_block = self._new_block("if_true")
        cfg.add_block(true_block)
        cfg.add_edge(block.block_id, true_block.block_id, "true")
        true_ends = self._process_body(node.body, true_block, exit_block, cfg)

        result = list(true_ends)

        if node.orelse:
            false_block = self._new_block("if_false")
            cfg.add_block(false_block)
            cfg.add_edge(block.block_id, false_block.block_id, "false")
            false_ends = self._process_body(node.orelse, false_block, exit_block, cfg)
            result.extend(false_ends)
        else:
            result.append(block.block_id)

        return result

    def _handle_loop(
        self, node: ast.For | ast.While | ast.AsyncFor, block: BasicBlock, exit_block: BasicBlock, cfg: ControlFlowGraph
    ) -> list[int]:
        loop_type = type(node).__name__
        block.add_statement(node.lineno, loop_type)

        loop_body = self._new_block("loop_body")
        cfg.add_block(loop_body)
        cfg.add_edge(block.block_id, loop_body.block_id, "enter_loop")

        body_ends = self._process_body(node.body, loop_body, exit_block, cfg)
        for be in body_ends:
            cfg.add_edge(be, block.block_id, "loop_back")

        result = [block.block_id]  # loop condition can be false → exit

        if node.orelse:
            else_block = self._new_block("loop_else")
            cfg.add_block(else_block)
            cfg.add_edge(block.block_id, else_block.block_id, "loop_else")
            else_ends = self._process_body(node.orelse, else_block, exit_block, cfg)
            result.extend(else_ends)

        return result

    def _handle_try(
        self, node: ast.Try, block: BasicBlock, exit_block: BasicBlock, cfg: ControlFlowGraph
    ) -> list[int]:
        block.add_statement(node.lineno, "Try")

        try_body = self._new_block("try_body")
        cfg.add_block(try_body)
        cfg.add_edge(block.block_id, try_body.block_id, "try")
        body_ends = self._process_body(node.body, try_body, exit_block, cfg)

        result = list(body_ends)

        for handler in node.handlers:
            except_block = self._new_block(f"except_{self._handler_name(handler)}")
            cfg.add_block(except_block)
            cfg.add_edge(try_body.block_id, except_block.block_id, "except")
            handler_ends = self._process_body(handler.body, except_block, exit_block, cfg)
            result.extend(handler_ends)

        if node.finalbody:
            finally_block = self._new_block("finally")
            cfg.add_block(finally_block)
            for rb in result:
                cfg.add_edge(rb, finally_block.block_id, "finally")
            finally_ends = self._process_body(node.finalbody, finally_block, exit_block, cfg)
            return finally_ends

        return result

    def _new_block(self, label: str = "") -> BasicBlock:
        self._block_counter += 1
        return BasicBlock(block_id=self._block_counter, label=label)

    @staticmethod
    def _handler_name(handler: ast.ExceptHandler) -> str:
        if handler.type:
            if isinstance(handler.type, ast.Name):
                return handler.type.id
            return "multi"
        return "bare"
