"""
symbol_resolver — Cross-file symbol resolution using scope analysis.

Maps every ``Name`` reference to its definition site by following
Python's LEGB (Local → Enclosing → Global → Builtin) scope rules.
"""

from __future__ import annotations

import builtins
from dataclasses import dataclass, field
from typing import Any

from core_engine.ast_parser import ParsedModule, FunctionInfo, ClassInfo


@dataclass
class SymbolDefinition:
    """Where a symbol is defined."""
    name: str
    qualified_name: str
    kind: str  # "function", "class", "variable", "import", "parameter", "builtin"
    file_path: str
    lineno: int | None
    module: str | None = None  # for imports


@dataclass
class SymbolTable:
    """Complete symbol table for a workspace."""
    definitions: dict[str, list[SymbolDefinition]] = field(default_factory=dict)
    # Maps qualified name → definition for fast lookup
    _qname_index: dict[str, SymbolDefinition] = field(default_factory=dict)

    def add(self, sym: SymbolDefinition) -> None:
        self.definitions.setdefault(sym.name, []).append(sym)
        self._qname_index[sym.qualified_name] = sym

    def lookup(self, name: str) -> list[SymbolDefinition]:
        return self.definitions.get(name, [])

    def lookup_qualified(self, qname: str) -> SymbolDefinition | None:
        return self._qname_index.get(qname)

    @property
    def all_symbols(self) -> list[SymbolDefinition]:
        return list(self._qname_index.values())


# Built-in names for Python
_BUILTINS = set(dir(builtins))


class SymbolResolver:
    """Builds a whole-workspace symbol table from parsed modules."""

    def build_symbol_table(self, modules: list[ParsedModule]) -> SymbolTable:
        table = SymbolTable()

        for mod in modules:
            prefix = mod.module_name

            # Register functions
            for func in mod.functions:
                table.add(SymbolDefinition(
                    name=func.name,
                    qualified_name=f"{prefix}.{func.qualified_name}",
                    kind="function",
                    file_path=mod.file_path,
                    lineno=func.lineno,
                ))

            # Register classes + methods
            for cls in mod.classes:
                table.add(SymbolDefinition(
                    name=cls.name,
                    qualified_name=f"{prefix}.{cls.qualified_name}",
                    kind="class",
                    file_path=mod.file_path,
                    lineno=cls.lineno,
                ))
                for method in cls.methods:
                    table.add(SymbolDefinition(
                        name=method.name,
                        qualified_name=f"{prefix}.{method.qualified_name}",
                        kind="function",
                        file_path=mod.file_path,
                        lineno=method.lineno,
                    ))

            # Register imports
            for imp in mod.imports:
                for name in imp.names:
                    display = imp.alias or name
                    table.add(SymbolDefinition(
                        name=display,
                        qualified_name=f"{prefix}.<import>.{display}",
                        kind="import",
                        file_path=mod.file_path,
                        lineno=imp.lineno,
                        module=imp.module,
                    ))

            # Register global variables
            for var in mod.global_variables:
                if var and var not in _BUILTINS:
                    table.add(SymbolDefinition(
                        name=var,
                        qualified_name=f"{prefix}.{var}",
                        kind="variable",
                        file_path=mod.file_path,
                        lineno=None,
                    ))

        return table

    def resolve_name(self, name: str, table: SymbolTable) -> list[SymbolDefinition]:
        """Resolve a simple name across the entire workspace."""
        defs = table.lookup(name)
        if defs:
            return defs
        if name in _BUILTINS:
            return [SymbolDefinition(
                name=name,
                qualified_name=f"builtins.{name}",
                kind="builtin",
                file_path="<builtins>",
                lineno=None,
            )]
        return []

    def resolve_qualified_name(
        self,
        dotted_name: str,
        source_module: str,
        table: SymbolTable,
    ) -> SymbolDefinition | None:
        """Resolve a dotted name like ``os.path.join`` using the symbol table."""
        # Try direct qualified lookup
        candidate = table.lookup_qualified(dotted_name)
        if candidate:
            return candidate

        # Try prefixed with source module
        candidate = table.lookup_qualified(f"{source_module}.{dotted_name}")
        if candidate:
            return candidate

        # Try partial match: split on dots and look up the first part
        parts = dotted_name.split(".")
        for i in range(len(parts), 0, -1):
            partial = ".".join(parts[:i])
            hits = table.lookup(partial)
            if hits:
                return hits[0]

        return None
