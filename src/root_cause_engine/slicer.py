"""
slicer — Dynamic backward program slicing.

Given an execution trace and a failing variable at a failing line,
computes the minimal set of statements that could have influenced
that variable's value.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SliceResult:
    """Minimal set of statements that contributed to the failure."""
    failing_line: int
    failing_variable: str | None
    relevant_lines: set[int] = field(default_factory=set)
    relevant_variables: set[str] = field(default_factory=set)
    data_dependencies: list[tuple[int, str, int, str]] = field(default_factory=list)
    # (def_line, var, use_line, var)


class BackwardSlicer:
    """Computes backward program slices from execution traces."""

    def slice_from_trace(
        self,
        trace_events: list[dict[str, Any]],
        failing_line: int,
        failing_variable: str | None = None,
    ) -> SliceResult:
        """
        Compute the backward slice.

        Algorithm:
        1. Start from the failing line and variable
        2. Find all variables used at that line
        3. For each variable, find its most recent definition
        4. Recursively slice from each definition
        """
        result = SliceResult(
            failing_line=failing_line,
            failing_variable=failing_variable,
        )

        # Build a line → variables map from trace events
        line_vars: dict[int, dict[str, str]] = {}
        line_order: list[int] = []  # execution order

        for ev in trace_events:
            if ev.get("type") == "line" or ev.get("t") == "line":
                lineno = ev.get("line") or ev.get("l", 0)
                variables = ev.get("vars") or ev.get("v", {})
                line_vars[lineno] = variables
                line_order.append(lineno)

        if not line_order:
            return result

        # Initialize worklist
        worklist: list[tuple[int, str | None]] = [(failing_line, failing_variable)]
        visited: set[tuple[int, str | None]] = set()

        while worklist:
            current_line, current_var = worklist.pop()
            if (current_line, current_var) in visited:
                continue
            visited.add((current_line, current_var))
            result.relevant_lines.add(current_line)

            if current_var:
                result.relevant_variables.add(current_var)

            # Find the variables at this line
            vars_at_line = line_vars.get(current_line, {})

            # Find variable definitions that feed into this line
            if current_var and current_var in vars_at_line:
                # Search backwards for the previous definition of this variable
                prev_def = self._find_previous_definition(
                    current_var, current_line, line_order, line_vars
                )
                if prev_def is not None:
                    result.data_dependencies.append(
                        (prev_def, current_var, current_line, current_var)
                    )
                    worklist.append((prev_def, current_var))
            elif not current_var:
                # If no specific variable, include all variables at this line
                for var_name in vars_at_line:
                    prev_def = self._find_previous_definition(
                        var_name, current_line, line_order, line_vars
                    )
                    if prev_def is not None:
                        result.data_dependencies.append(
                            (prev_def, var_name, current_line, var_name)
                        )
                        worklist.append((prev_def, var_name))

        return result

    def _find_previous_definition(
        self,
        var_name: str,
        current_line: int,
        line_order: list[int],
        line_vars: dict[int, dict[str, str]],
    ) -> int | None:
        """Find the most recent line before current_line where var_name changed."""
        prev_value = None
        prev_line = None

        # Walk the execution order up to current_line
        for exec_line in line_order:
            if exec_line == current_line:
                break
            vars_at = line_vars.get(exec_line, {})
            if var_name in vars_at:
                current_value = vars_at[var_name]
                if current_value != prev_value:
                    prev_value = current_value
                    prev_line = exec_line

        return prev_line

    def slice_from_source(
        self,
        source: str,
        target_line: int,
        target_variable: str | None = None,
    ) -> SliceResult:
        """Static backward slice from source code AST (no execution trace needed)."""
        result = SliceResult(
            failing_line=target_line,
            failing_variable=target_variable,
        )

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return result

        # Build a line → AST node map
        assignments: dict[str, list[int]] = {}  # var → [definition lines]
        usages: dict[int, set[str]] = {}  # line → {used variables}

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assignments.setdefault(target.id, []).append(node.lineno)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                usages.setdefault(node.lineno, set()).add(node.id)

        # Backward slice from target_line
        worklist: list[int] = [target_line]
        visited_lines: set[int] = set()

        while worklist:
            line = worklist.pop()
            if line in visited_lines:
                continue
            visited_lines.add(line)
            result.relevant_lines.add(line)

            # Get variables used at this line
            used_vars = usages.get(line, set())
            if target_variable and line == target_line:
                used_vars = {target_variable}

            for var in used_vars:
                result.relevant_variables.add(var)
                # Find definitions of this variable before this line
                defs = assignments.get(var, [])
                for def_line in defs:
                    if def_line < line:
                        worklist.append(def_line)
                        result.data_dependencies.append(
                            (def_line, var, line, var)
                        )

        return result
