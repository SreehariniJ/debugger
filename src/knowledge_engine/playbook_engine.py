"""
playbook_engine — Structured debugging playbooks for common error types.

Playbooks encode expert debugging procedures as step-by-step plans
that agents can follow when diagnosing specific error categories.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PlaybookStep:
    action: str
    description: str
    template: str | None = None
    agent: str | None = None  # which agent should execute this step


@dataclass
class Playbook:
    name: str
    triggers: list[str]
    steps: list[PlaybookStep]
    severity: str = "WARNING"
    description: str = ""

    def matches(self, error_text: str) -> bool:
        error_lower = error_text.lower()
        return any(t.lower() in error_lower for t in self.triggers)


class PlaybookEngine:
    """Manages and matches debugging playbooks."""

    def __init__(self) -> None:
        self._playbooks: list[Playbook] = []
        self._load_defaults()

    def load_from_directory(self, directory: str | Path) -> int:
        """Load playbooks from JSON files in a directory."""
        path = Path(directory)
        if not path.exists():
            return 0

        count = 0
        for f in path.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                pb = Playbook(
                    name=data.get("name", f.stem),
                    triggers=data.get("triggers", []),
                    steps=[
                        PlaybookStep(
                            action=s.get("action", ""),
                            description=s.get("description", ""),
                            template=s.get("template"),
                            agent=s.get("agent"),
                        )
                        for s in data.get("steps", [])
                    ],
                    severity=data.get("severity", "WARNING"),
                    description=data.get("description", ""),
                )
                self._playbooks.append(pb)
                count += 1
            except (json.JSONDecodeError, OSError):
                continue
        return count

    def find_playbook(self, error_text: str) -> Playbook | None:
        """Find the first matching playbook for an error."""
        for pb in self._playbooks:
            if pb.matches(error_text):
                return pb
        return None

    def find_all_playbooks(self, error_text: str) -> list[Playbook]:
        """Find all matching playbooks for an error."""
        return [pb for pb in self._playbooks if pb.matches(error_text)]

    def get_all(self) -> list[Playbook]:
        return list(self._playbooks)

    def to_dict(self) -> list[dict[str, Any]]:
        return [
            {
                "name": pb.name,
                "triggers": pb.triggers,
                "severity": pb.severity,
                "steps": [
                    {"action": s.action, "description": s.description, "template": s.template}
                    for s in pb.steps
                ],
            }
            for pb in self._playbooks
        ]

    def _load_defaults(self) -> None:
        """Built-in playbooks for the most common Python errors."""
        defaults = [
            Playbook(
                name="ZeroDivisionError",
                triggers=["ZeroDivisionError", "division by zero"],
                severity="CRITICAL",
                steps=[
                    PlaybookStep("identify_denominator", "Find the variable used as denominator in the division"),
                    PlaybookStep("trace_value", "Trace the denominator's value through execution to find where it becomes zero"),
                    PlaybookStep("add_guard", "Add a zero-check before the division", template="if {denominator} != 0:\n    result = {numerator} / {denominator}\nelse:\n    result = 0"),
                    PlaybookStep("verify", "Run the fixed code to verify the error is resolved", agent="CriticAgent"),
                ],
            ),
            Playbook(
                name="NameError",
                triggers=["NameError", "is not defined"],
                severity="WARNING",
                steps=[
                    PlaybookStep("check_spelling", "Compare the undefined name against all defined variables in scope"),
                    PlaybookStep("check_imports", "Verify all required modules are imported"),
                    PlaybookStep("check_scope", "Ensure the variable is defined before it is used in the current scope"),
                    PlaybookStep("fix_definition", "Add the missing definition or correct the spelling"),
                ],
            ),
            Playbook(
                name="TypeError",
                triggers=["TypeError"],
                severity="WARNING",
                steps=[
                    PlaybookStep("identify_types", "Determine the actual types of all operands in the failing expression"),
                    PlaybookStep("trace_origin", "Trace where each operand received its current type"),
                    PlaybookStep("add_conversion", "Add appropriate type conversion or validation"),
                ],
            ),
            Playbook(
                name="IndexError",
                triggers=["IndexError", "index out of range"],
                severity="WARNING",
                steps=[
                    PlaybookStep("check_length", "Verify the sequence length before the failing access"),
                    PlaybookStep("check_loop_bounds", "Check loop boundaries for off-by-one errors"),
                    PlaybookStep("add_bounds_check", "Add len() check before index access", template="if index < len({sequence}):\n    value = {sequence}[index]"),
                ],
            ),
            Playbook(
                name="ImportError",
                triggers=["ImportError", "ModuleNotFoundError", "No module named"],
                severity="WARNING",
                steps=[
                    PlaybookStep("check_installed", "Verify the package is installed in the environment"),
                    PlaybookStep("check_path", "Check sys.path includes the module's location"),
                    PlaybookStep("check_circular", "Look for circular import patterns in the dependency graph"),
                    PlaybookStep("fix_import", "Install missing package or restructure imports"),
                ],
            ),
            Playbook(
                name="RecursionError",
                triggers=["RecursionError", "maximum recursion depth"],
                severity="CRITICAL",
                steps=[
                    PlaybookStep("identify_recursive_func", "Find the recursive function in the call stack"),
                    PlaybookStep("check_base_case", "Verify the function has a proper base case"),
                    PlaybookStep("check_convergence", "Ensure recursive calls reduce the problem toward the base case"),
                    PlaybookStep("fix_recursion", "Add or correct the base case condition"),
                ],
            ),
        ]
        self._playbooks.extend(defaults)
