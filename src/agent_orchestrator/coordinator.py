"""
coordinator — Central orchestration for the multi-agent debugging pipeline.

Replaces the linear ``viper_orchestration`` with a graph-based
coordinator that manages agent lifecycle, task routing, parallel
execution, and consensus-driven decision making.
"""

from __future__ import annotations

import ast
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_orchestrator.message_bus import MessageBus, AgentMessage
from agent_orchestrator.consensus import ConsensusEngine, Vote, ConsensusResult

logger = logging.getLogger("orchestrator")


# ---------------------------------------------------------------------------
# Data Contracts
# ---------------------------------------------------------------------------

@dataclass
class DebugTask:
    """Input to the orchestration pipeline."""
    target_file: str | None = None
    code_snippet: str | None = None
    error_message: str | None = None
    mode: str = "full"  # "full" or "fast"
    enable_tracing: bool = True
    enable_profiling: bool = False
    max_fix_attempts: int = 3


@dataclass
class DebugReport:
    """Output from the orchestration pipeline."""
    request_id: str = ""
    success: bool = False
    analysis: str = ""
    explanation: str = ""
    root_cause_line: int | None = None
    root_cause_file: str | None = None
    fixed_code: str | None = None
    diff: str | None = None
    severity: str | None = None
    confidence: int | None = None
    execution_trace_summary: dict[str, Any] | None = None
    profiling_summary: dict[str, Any] | None = None
    security_report: dict[str, Any] | None = None
    patch_validation: dict[str, Any] | None = None
    agent_timeline: list[dict[str, Any]] = field(default_factory=list)
    knowledge_context: str = ""
    pipeline_log: list[dict[str, str]] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "success": self.success,
            "analysis": self.analysis,
            "explanation": self.explanation,
            "root_cause_line": self.root_cause_line,
            "root_cause_file": self.root_cause_file,
            "fixed_code": self.fixed_code,
            "diff": self.diff,
            "severity": self.severity,
            "confidence": self.confidence,
            "execution_trace": self.execution_trace_summary,
            "profiling": self.profiling_summary,
            "security": self.security_report,
            "patch_validation": self.patch_validation,
            "agent_timeline": self.agent_timeline,
            "pipeline_log": self.pipeline_log,
            "metrics": self.metrics,
        }


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------

class Coordinator:
    """
    Orchestrates the multi-agent debugging pipeline.

    Pipeline phases:
    1. ANALYZE — AnalyzerAgent classifies the error
    2. RESEARCH — ResearcherAgent finds related workspace files
    3. TRACE — RuntimeDebuggerAgent executes with tracing
    4. LOCALIZE — RootCauseAgent identifies the fault origin
    5. FIX — FixerAgent generates candidate patches
    6. VALIDATE — CriticAgent + SecurityAgent validate patches
    7. PROFILE — PerformanceAgent profiles (optional)

    In "fast" mode, phases 3, 4, and 7 are skipped.
    """

    def __init__(
        self,
        agents_module: Any = None,
        workspace_root: str | None = None,
    ):
        self.agents_module = agents_module
        self.workspace_root = workspace_root
        self.bus = MessageBus()
        self.consensus = ConsensusEngine()

    async def run(self, task: DebugTask) -> DebugReport:
        """Execute the full debugging pipeline."""
        report = DebugReport(request_id=f"dbg-{int(time.time())}")
        start_time = time.monotonic()
        log = report.pipeline_log

        try:
            # Read source code
            code = self._get_code(task)
            if not code:
                report.analysis = "No code provided"
                return report

            log.append(self._log("INFO", "Pipeline started", f"mode={task.mode}"))

            # Phase 1: ANALYZE
            analysis = await self._phase_analyze(code, task, report, log)

            # Phase 2: RESEARCH (parallel with analyze in future)
            await self._phase_research(code, task, report, log)

            # Phase 3: TRACE (full mode only)
            if task.mode == "full" and task.enable_tracing and task.target_file:
                await self._phase_trace(task, report, log)

            # Phase 4: ROOT CAUSE (full mode only)
            if task.mode == "full" and report.execution_trace_summary:
                await self._phase_localize(code, task, report, log)

            # Phase 5: FIX
            await self._phase_fix(code, task, report, log)

            # Phase 6: VALIDATE
            if report.fixed_code:
                await self._phase_validate(code, report, log)

            # Phase 7: PROFILE (optional)
            if task.enable_profiling and task.target_file:
                await self._phase_profile(task, report, log)

            report.success = report.fixed_code is not None
            log.append(self._log("INFO", "Pipeline complete", f"success={report.success}"))

        except Exception as exc:
            logger.exception("Pipeline error: %s", exc)
            report.analysis = f"Pipeline error: {exc}"
            log.append(self._log("ERROR", "Pipeline error", str(exc)))

        report.metrics["total_time_ms"] = round((time.monotonic() - start_time) * 1000, 1)
        return report

    # --- Pipeline Phases ---

    async def _phase_analyze(self, code: str, task: DebugTask, report: DebugReport, log: list) -> str:
        log.append(self._log("INFO", "Phase ANALYZE", "Classifying error"))
        t0 = time.monotonic()

        if self.agents_module:
            try:
                analysis, explanation = self.agents_module.analyzer_agent(code)
                report.analysis = analysis
                report.explanation = explanation
            except Exception as exc:
                report.analysis = f"Analysis failed: {exc}"
                report.explanation = ""
        else:
            report.analysis = self._heuristic_analyze(code, task.error_message)
            report.explanation = "Heuristic analysis (no LLM loaded)"

        elapsed = round((time.monotonic() - t0) * 1000, 1)
        report.agent_timeline.append({"agent": "AnalyzerAgent", "phase": "ANALYZE", "duration_ms": elapsed})
        log.append(self._log("INFO", "ANALYZE complete", f"{elapsed}ms"))
        return report.analysis

    async def _phase_research(self, code: str, task: DebugTask, report: DebugReport, log: list) -> None:
        log.append(self._log("INFO", "Phase RESEARCH", "Finding related files"))
        t0 = time.monotonic()

        # Use knowledge engine for context
        try:
            from knowledge_engine import SemanticIndex
            index = SemanticIndex()
            index.load_and_index(self.workspace_root or ".")
            context = index.query_text(report.analysis or code[:200])
            report.knowledge_context = context
        except Exception:
            report.knowledge_context = ""

        elapsed = round((time.monotonic() - t0) * 1000, 1)
        report.agent_timeline.append({"agent": "ResearcherAgent", "phase": "RESEARCH", "duration_ms": elapsed})

    async def _phase_trace(self, task: DebugTask, report: DebugReport, log: list) -> None:
        log.append(self._log("INFO", "Phase TRACE", "Executing with tracing"))
        t0 = time.monotonic()

        try:
            from runtime_debugger import TraceEngine
            engine = TraceEngine(workspace_root=self.workspace_root)
            trace = engine.trace_file(task.target_file)
            report.execution_trace_summary = trace.to_dict()
            if trace.error_message:
                report.analysis = f"{report.analysis} | Runtime: {trace.error_message}"
        except Exception as exc:
            log.append(self._log("WARN", "Tracing failed", str(exc)))

        elapsed = round((time.monotonic() - t0) * 1000, 1)
        report.agent_timeline.append({"agent": "RuntimeDebuggerAgent", "phase": "TRACE", "duration_ms": elapsed})

    async def _phase_localize(self, code: str, task: DebugTask, report: DebugReport, log: list) -> None:
        log.append(self._log("INFO", "Phase LOCALIZE", "Root cause analysis"))
        t0 = time.monotonic()

        try:
            from root_cause_engine import FaultLocalizer
            localizer = FaultLocalizer()
            trace_events = (report.execution_trace_summary or {}).get("events", [])
            rc_report = localizer.localize(
                trace_events=trace_events,
                error_message=report.analysis,
                source=code,
                crash_line=None,
                crash_file=task.target_file,
            )
            if rc_report.top_candidate:
                report.root_cause_line = rc_report.top_candidate.lineno
                report.root_cause_file = rc_report.top_candidate.filename
        except Exception as exc:
            log.append(self._log("WARN", "Root cause analysis failed", str(exc)))

        elapsed = round((time.monotonic() - t0) * 1000, 1)
        report.agent_timeline.append({"agent": "RootCauseAgent", "phase": "LOCALIZE", "duration_ms": elapsed})

    async def _phase_fix(self, code: str, task: DebugTask, report: DebugReport, log: list) -> None:
        log.append(self._log("INFO", "Phase FIX", "Generating patches"))
        t0 = time.monotonic()

        context = f"Analysis: {report.analysis}\n"
        if report.knowledge_context:
            context += f"Knowledge: {report.knowledge_context[:500]}\n"
        if report.root_cause_line:
            context += f"Root cause: line {report.root_cause_line}\n"

        for attempt in range(1, task.max_fix_attempts + 1):
            try:
                if self.agents_module:
                    fixed_code = await self.agents_module.code_fixer_agent_async(
                        code, report.analysis, context
                    )
                    if fixed_code and fixed_code.strip() != code.strip():
                        report.fixed_code = fixed_code
                        break
                else:
                    log.append(self._log("WARN", "No LLM available", "Skipping fix generation"))
                    break
            except Exception as exc:
                log.append(self._log("WARN", f"Fix attempt {attempt} failed", str(exc)))

        elapsed = round((time.monotonic() - t0) * 1000, 1)
        report.agent_timeline.append({"agent": "FixerAgent", "phase": "FIX", "duration_ms": elapsed})

    async def _phase_validate(self, original_code: str, report: DebugReport, log: list) -> None:
        log.append(self._log("INFO", "Phase VALIDATE", "Validating patch"))
        t0 = time.monotonic()
        votes: list[Vote] = []

        # Stage 1: Syntax validation
        try:
            ast.parse(report.fixed_code)
            votes.append(Vote(agent="SyntaxValidator", decision="approve", confidence=1.0, reason="Syntax OK"))
        except SyntaxError as exc:
            votes.append(Vote(agent="SyntaxValidator", decision="reject", confidence=1.0, reason=f"SyntaxError: {exc}", has_veto=True))

        # Stage 2: Critic agent
        if self.agents_module:
            try:
                critique = self.agents_module.critic_agent(original_code, report.fixed_code)
                if critique and "approved" in str(critique).lower():
                    votes.append(Vote(agent="CriticAgent", decision="approve", confidence=0.8, reason=str(critique)[:200], has_veto=True))
                else:
                    votes.append(Vote(agent="CriticAgent", decision="reject", confidence=0.7, reason=str(critique)[:200], has_veto=True))
            except Exception:
                votes.append(Vote(agent="CriticAgent", decision="abstain", confidence=0.0, reason="Critic unavailable"))

        # Stage 3: Security check
        if self.agents_module:
            try:
                sec_result = self.agents_module.security_audit_agent(report.fixed_code)
                is_secure = sec_result.get("is_secure", True) if isinstance(sec_result, dict) else True
                if is_secure:
                    votes.append(Vote(agent="SecurityAgent", decision="approve", confidence=0.9, reason="No vulnerabilities found", has_veto=True))
                else:
                    votes.append(Vote(agent="SecurityAgent", decision="reject", confidence=0.9, reason="Security issues detected", has_veto=True))
            except Exception:
                votes.append(Vote(agent="SecurityAgent", decision="abstain", confidence=0.0, reason="Security check unavailable"))

        # Consensus
        result = self.consensus.vote(votes)
        report.patch_validation = {
            "decision": result.decision,
            "for": result.for_count,
            "against": result.against_count,
            "abstain": result.abstain_count,
            "vetoed_by": result.vetoed_by,
            "avg_confidence": round(result.avg_confidence, 2),
            "ready_to_apply": result.decision == "approved",
            "issues": [v.reason for v in votes if v.decision == "reject"],
        }

        if result.decision != "approved":
            log.append(self._log("WARN", "Patch rejected", f"by consensus: {result.vetoed_by or 'majority'}"))
            report.fixed_code = None  # Discard rejected patch

        elapsed = round((time.monotonic() - t0) * 1000, 1)
        report.agent_timeline.append({"agent": "Validator", "phase": "VALIDATE", "duration_ms": elapsed})

    async def _phase_profile(self, task: DebugTask, report: DebugReport, log: list) -> None:
        log.append(self._log("INFO", "Phase PROFILE", "Profiling execution"))
        t0 = time.monotonic()

        try:
            from profiling_engine import CPUProfiler
            profiler = CPUProfiler()
            p_report = profiler.profile_file(task.target_file)
            report.profiling_summary = p_report.to_dict()
        except Exception as exc:
            log.append(self._log("WARN", "Profiling failed", str(exc)))

        elapsed = round((time.monotonic() - t0) * 1000, 1)
        report.agent_timeline.append({"agent": "PerformanceAgent", "phase": "PROFILE", "duration_ms": elapsed})

    # --- Utilities ---

    def _get_code(self, task: DebugTask) -> str | None:
        if task.code_snippet:
            return task.code_snippet
        if task.target_file:
            try:
                return Path(task.target_file).read_text(encoding="utf-8", errors="replace")
            except OSError:
                return None
        return None

    @staticmethod
    def _heuristic_analyze(code: str, error_msg: str | None) -> str:
        """Quick heuristic analysis when no LLM is available."""
        issues = []
        for i, line in enumerate(code.splitlines(), 1):
            stripped = line.strip()
            if "eval(" in stripped:
                issues.append(f"L{i}: eval() usage detected")
            if "exec(" in stripped:
                issues.append(f"L{i}: exec() usage detected")
            if "except:" in stripped and "except Exception" not in stripped:
                issues.append(f"L{i}: bare except clause")
        if error_msg:
            issues.insert(0, f"Error: {error_msg}")
        return "; ".join(issues[:5]) if issues else "No immediately obvious issues found"

    @staticmethod
    def _log(level: str, phase: str, message: str) -> dict[str, str]:
        return {
            "timestamp": time.strftime("%H:%M:%S"),
            "level": level,
            "message": f"[{phase}] {message}",
        }
