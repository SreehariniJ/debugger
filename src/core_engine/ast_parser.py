"""
ast_parser — Deep AST analysis for Python source files.

Extracts structured information (functions, classes, imports, calls,
assignments) from parsed ASTs.  The output feeds into the symbol
resolver, dependency graph builder, and call graph builder.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data classes representing parsed information
# ---------------------------------------------------------------------------

@dataclass
class FunctionInfo:
    name: str
    qualified_name: str
    lineno: int
    end_lineno: int | None
    args: list[str]
    decorators: list[str]
    is_async: bool
    docstring: str | None
    complexity: int = 0  # populated later


@dataclass
class ClassInfo:
    name: str
    qualified_name: str
    lineno: int
    end_lineno: int | None
    bases: list[str]
    methods: list[FunctionInfo]
    docstring: str | None


@dataclass
class ImportInfo:
    module: str | None
    names: list[str]
    alias: str | None
    lineno: int
    is_from_import: bool


@dataclass
class CallSite:
    """Represents a function/method call found during AST analysis."""
    caller: str  # qualified name of enclosing function (or "<module>")
    callee_raw: str  # raw text of the thing being called (e.g. "os.path.join")
    lineno: int
    col_offset: int


@dataclass
class AssignmentInfo:
    targets: list[str]
    lineno: int
    scope: str  # qualified name of enclosing scope


@dataclass
class ParsedModule:
    """Complete parsed representation of a single Python module."""
    file_path: str
    module_name: str
    source_hash: str
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    calls: list[CallSite] = field(default_factory=list)
    assignments: list[AssignmentInfo] = field(default_factory=list)
    global_variables: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    loc: int = 0
    sloc: int = 0


# ---------------------------------------------------------------------------
# Parser implementation
# ---------------------------------------------------------------------------

class ASTParser:
    """Parses source files into rich ``ParsedModule`` descriptors."""

    def parse_file(self, file_path: str | Path) -> ParsedModule:
        path = Path(file_path)
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return ParsedModule(
                file_path=str(path),
                module_name=path.stem,
                source_hash="",
                errors=[f"Cannot read file: {exc}"],
            )
        return self.parse_source(source, str(path))

    def parse_source(self, source: str, file_path: str = "<string>") -> ParsedModule:
        source_hash = hashlib.sha256(source.encode("utf-8", errors="replace")).hexdigest()
        module_name = Path(file_path).stem if file_path != "<string>" else "<string>"

        lines = source.splitlines()
        loc = len(lines)
        sloc = sum(1 for line in lines if line.strip() and not line.strip().startswith("#"))

        module = ParsedModule(
            file_path=file_path,
            module_name=module_name,
            source_hash=source_hash,
            loc=loc,
            sloc=sloc,
        )

        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError as exc:
            module.errors.append(f"SyntaxError: {exc}")
            return module

        self._extract_module_level(tree, module)
        return module

    # ----- extraction helpers ------------------------------------------------

    def _extract_module_level(self, tree: ast.Module, module: ParsedModule) -> None:
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fi = self._extract_function(node, scope="")
                module.functions.append(fi)
                self._collect_calls(node, fi.qualified_name, module)
            elif isinstance(node, ast.ClassDef):
                ci = self._extract_class(node, scope="")
                module.classes.append(ci)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                module.imports.extend(self._extract_imports(node))
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                ai = self._extract_assignment(node, scope="<module>")
                if ai:
                    module.assignments.append(ai)
                    module.global_variables.extend(ai.targets)

        # Collect top-level calls (e.g. `if __name__ == "__main__": main()`)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                cs = self._make_call_site(node, "<module>")
                if cs:
                    module.calls.append(cs)

    def _extract_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, scope: str) -> FunctionInfo:
        qname = f"{scope}.{node.name}" if scope else node.name
        args = [a.arg for a in node.args.args]
        decorators = [self._name_of(d) for d in node.decorator_list]
        docstring = ast.get_docstring(node)
        complexity = self._cyclomatic_complexity(node)

        return FunctionInfo(
            name=node.name,
            qualified_name=qname,
            lineno=node.lineno,
            end_lineno=getattr(node, "end_lineno", None),
            args=args,
            decorators=decorators,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            docstring=docstring,
            complexity=complexity,
        )

    def _extract_class(self, node: ast.ClassDef, scope: str) -> ClassInfo:
        qname = f"{scope}.{node.name}" if scope else node.name
        bases = [self._name_of(b) for b in node.bases]
        docstring = ast.get_docstring(node)
        methods: list[FunctionInfo] = []
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(self._extract_function(child, scope=qname))
        return ClassInfo(
            name=node.name,
            qualified_name=qname,
            lineno=node.lineno,
            end_lineno=getattr(node, "end_lineno", None),
            bases=bases,
            methods=methods,
            docstring=docstring,
        )

    def _extract_imports(self, node: ast.Import | ast.ImportFrom) -> list[ImportInfo]:
        results: list[ImportInfo] = []
        if isinstance(node, ast.Import):
            for alias in node.names:
                results.append(ImportInfo(
                    module=alias.name,
                    names=[alias.name],
                    alias=alias.asname,
                    lineno=node.lineno,
                    is_from_import=False,
                ))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                results.append(ImportInfo(
                    module=module,
                    names=[alias.name],
                    alias=alias.asname,
                    lineno=node.lineno,
                    is_from_import=True,
                ))
        return results

    def _extract_assignment(self, node: ast.Assign | ast.AnnAssign, scope: str) -> AssignmentInfo | None:
        targets: list[str] = []
        if isinstance(node, ast.Assign):
            for t in node.targets:
                targets.append(self._name_of(t))
        elif isinstance(node, ast.AnnAssign) and node.target:
            targets.append(self._name_of(node.target))
        if targets:
            return AssignmentInfo(targets=targets, lineno=node.lineno, scope=scope)
        return None

    def _collect_calls(self, func_node: ast.AST, scope: str, module: ParsedModule) -> None:
        for node in ast.walk(func_node):
            if isinstance(node, ast.Call):
                cs = self._make_call_site(node, scope)
                if cs:
                    module.calls.append(cs)

    def _make_call_site(self, node: ast.Call, caller: str) -> CallSite | None:
        callee = self._name_of(node.func)
        if not callee:
            return None
        return CallSite(
            caller=caller,
            callee_raw=callee,
            lineno=node.lineno,
            col_offset=node.col_offset,
        )

    # ----- utilities ---------------------------------------------------------

    @staticmethod
    def _name_of(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = ASTParser._name_of(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        if isinstance(node, ast.Constant):
            return str(node.value)
        if isinstance(node, ast.Subscript):
            return ASTParser._name_of(node.value)
        return ""

    @staticmethod
    def _cyclomatic_complexity(node: ast.AST) -> int:
        """McCabe cyclomatic complexity: count decision points + 1."""
        decision_types = (ast.If, ast.For, ast.While, ast.AsyncFor,
                          ast.ExceptHandler, ast.With, ast.AsyncWith,
                          ast.BoolOp, ast.Assert)
        count = 1
        for child in ast.walk(node):
            if isinstance(child, decision_types):
                count += 1
            if isinstance(child, ast.BoolOp):
                # Each additional boolean operand adds a path
                count += len(child.values) - 1
        return count
