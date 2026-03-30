"""
fault_localizer — Multi-signal root cause scoring.

Combines backward slicing, exception propagation, deviation analysis,
and dependency recency to score candidate root cause lines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from root_cause_engine.slicer import BackwardSlicer, SliceResult


@dataclass
class RootCauseCandidate:
    lineno: int
    filename: str
    score: float
    reasons: list[str] = field(default_factory=list)
    variable: str | None = None


@dataclass
class RootCauseReport:
    candidates: list[RootCauseCandidate] = field(default_factory=list)
    crash_line: int | None = None
    crash_file: str | None = None
    error_message: str | None = None
    slice_result: SliceResult | None = None
    exception_chain: list[dict[str, Any]] = field(default_factory=list)

    @property
    def top_candidate(self) -> RootCauseCandidate | None:
        return self.candidates[0] if self.candidates else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "crash_line": self.crash_line,
            "crash_file": self.crash_file,
            "error_message": self.error_message,
            "candidates": [
                {
                    "line": c.lineno,
                    "file": c.filename,
                    "score": round(c.score, 3),
                    "reasons": c.reasons,
                    "variable": c.variable,
                }
                for c in self.candidates[:10]
            ],
            "slice_size": len(self.slice_result.relevant_lines) if self.slice_result else 0,
            "exception_chain_length": len(self.exception_chain),
        }


class FaultLocalizer:
    """
    Multi-signal root cause analysis engine.

    Scoring formula:
        SCORE(line) = 0.4 × in_backward_slice
                    + 0.3 × is_exception_origin
                    + 0.2 × is_anomaly_point
                    + 0.1 × execution_frequency_anomaly
    """

    WEIGHT_SLICE = 0.4
    WEIGHT_EXCEPTION = 0.3
    WEIGHT_ANOMALY = 0.2
    WEIGHT_FREQUENCY = 0.1

    def __init__(self) -> None:
        self._slicer = BackwardSlicer()

    def localize(
        self,
        trace_events: list[dict[str, Any]],
        error_message: str | None = None,
        source: str | None = None,
        crash_line: int | None = None,
        crash_file: str | None = None,
    ) -> RootCauseReport:
        report = RootCauseReport(
            crash_line=crash_line,
            crash_file=crash_file,
            error_message=error_message,
        )

        # Phase 1: Find exception events
        exception_events = [
            ev for ev in trace_events
            if (ev.get("type") or ev.get("t")) == "exception"
        ]
        for ev in exception_events:
            report.exception_chain.append({
                "line": ev.get("line") or ev.get("l"),
                "file": ev.get("file") or ev.get("f"),
                "exception": ev.get("exception") or ev.get("ex"),
            })

        # Determine crash location
        if not crash_line and exception_events:
            crash_line = exception_events[0].get("line") or exception_events[0].get("l")
            crash_file = exception_events[0].get("file") or exception_events[0].get("f")
            report.crash_line = crash_line
            report.crash_file = crash_file

        if not crash_line:
            return report

        # Phase 2: Backward slice
        slice_result = self._slicer.slice_from_trace(
            trace_events, crash_line, failing_variable=None
        )
        report.slice_result = slice_result

        # Phase 3: Build line hit counts
        line_hits: dict[int, int] = {}
        for ev in trace_events:
            if (ev.get("type") or ev.get("t")) == "line":
                lineno = ev.get("line") or ev.get("l", 0)
                line_hits[lineno] = line_hits.get(lineno, 0) + 1

        avg_hits = sum(line_hits.values()) / max(len(line_hits), 1)

        # Phase 4: Score each candidate line
        exception_lines = {
            ev.get("line") or ev.get("l")
            for ev in exception_events
        }

        scored: dict[int, RootCauseCandidate] = {}
        filename = crash_file or "<unknown>"

        for lineno in slice_result.relevant_lines:
            score = 0.0
            reasons: list[str] = []

            # Signal 1: In backward slice
            score += self.WEIGHT_SLICE
            reasons.append("in backward slice")

            # Signal 2: Is an exception origin
            if lineno in exception_lines:
                score += self.WEIGHT_EXCEPTION
                reasons.append("exception raised here")

            # Signal 3: Anomaly (line that was hit unexpectedly few/many times)
            hits = line_hits.get(lineno, 0)
            if hits > avg_hits * 3:
                score += self.WEIGHT_ANOMALY * 0.5
                reasons.append(f"hot line ({hits} hits vs avg {avg_hits:.0f})")
            elif hits == 1 and avg_hits > 5:
                score += self.WEIGHT_ANOMALY
                reasons.append("rarely executed line")

            # Signal 4: Execution frequency anomaly
            if lineno != crash_line and lineno in exception_lines:
                score += self.WEIGHT_FREQUENCY
                reasons.append("upstream exception origin")

            scored[lineno] = RootCauseCandidate(
                lineno=lineno,
                filename=filename,
                score=score,
                reasons=reasons,
            )

        # Sort by score descending
        report.candidates = sorted(
            scored.values(), key=lambda c: c.score, reverse=True
        )

        return report
