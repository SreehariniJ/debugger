"""
report_generator — Generates structured debugging reports from sessions.
"""

from __future__ import annotations

import time
from typing import Any

from session_manager.session_recorder import DebugSession


class ReportGenerator:
    """Generates Markdown debugging reports from completed sessions."""

    def generate_markdown(self, session: DebugSession) -> str:
        lines: list[str] = []
        lines.append(f"# Debugging Report: {session.session_id}")
        lines.append("")
        lines.append(f"**Target File:** `{session.target_file}`")
        lines.append(f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(session.started_at))}")
        lines.append(f"**Duration:** {session.duration_seconds}s")
        lines.append(f"**Severity:** {session.severity or 'N/A'}")
        lines.append(f"**Confidence:** {session.confidence or 'N/A'}/10")
        lines.append("")

        # Error
        if session.error_message:
            lines.append("## Error")
            lines.append(f"```\n{session.error_message}\n```")
            lines.append("")

        # Root Cause
        if session.root_cause_line:
            lines.append("## Root Cause")
            lines.append(f"- **File:** `{session.root_cause_file or session.target_file}`")
            lines.append(f"- **Line:** {session.root_cause_line}")
            lines.append("")

        # Agent Pipeline
        if session.agent_interactions:
            lines.append("## Agent Pipeline")
            lines.append("| Agent | Action | Duration |")
            lines.append("| :--- | :--- | :--- |")
            for interaction in session.agent_interactions:
                lines.append(
                    f"| {interaction.agent_name} | {interaction.action} | {interaction.duration_ms:.0f}ms |"
                )
            lines.append("")

        # Patches
        if session.patches:
            lines.append("## Patch Attempts")
            for patch in session.patches:
                status = "✅ Passed" if patch.passed_validation else f"❌ Failed: {patch.rejection_reason}"
                lines.append(f"- Attempt {patch.attempt}: {status}")
            lines.append("")

        # Fix
        if session.final_fix:
            lines.append("## Applied Fix")
            lines.append(f"```python\n{session.final_fix}\n```")
            lines.append("")

        # Metrics
        if session.metrics:
            lines.append("## Performance Metrics")
            for key, value in session.metrics.items():
                lines.append(f"- **{key}:** {value}")
            lines.append("")

        return "\n".join(lines)

    def generate_bug_report(self, session: DebugSession) -> dict[str, Any]:
        """Generate a structured bug report suitable for issue trackers."""
        return {
            "title": f"Bug in {session.target_file}: {session.error_message or 'Unknown error'}",
            "severity": session.severity or "UNKNOWN",
            "file": session.target_file,
            "line": session.root_cause_line,
            "error": session.error_message,
            "reproduction": f"Run: python {session.target_file}",
            "root_cause": f"Line {session.root_cause_line} in {session.root_cause_file or session.target_file}" if session.root_cause_line else "Unknown",
            "suggested_fix": session.final_fix[:500] if session.final_fix else "No fix generated",
            "confidence": session.confidence,
            "agent_summary": [
                f"{i.agent_name}: {i.action}" for i in session.agent_interactions
            ],
            "generated_at": time.time(),
        }
