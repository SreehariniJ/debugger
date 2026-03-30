"""
session_recorder — Records and persists debugging sessions.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class AgentInteraction:
    agent_name: str
    action: str
    input_summary: str
    output_summary: str
    duration_ms: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class PatchCandidate:
    code: str
    attempt: int
    passed_validation: bool
    rejection_reason: str | None = None


@dataclass
class DebugSession:
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None
    target_file: str = ""
    error_message: str | None = None
    agent_interactions: list[AgentInteraction] = field(default_factory=list)
    root_cause_line: int | None = None
    root_cause_file: str | None = None
    patches: list[PatchCandidate] = field(default_factory=list)
    final_fix: str | None = None
    fix_applied: bool = False
    severity: str | None = None
    confidence: int | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        end = self.ended_at or time.time()
        return round(end - self.started_at, 3)

    def add_interaction(self, agent: str, action: str, input_s: str, output_s: str, duration_ms: float) -> None:
        self.agent_interactions.append(AgentInteraction(
            agent_name=agent, action=action,
            input_summary=input_s[:500], output_summary=output_s[:500],
            duration_ms=duration_ms,
        ))

    def add_patch(self, code: str, attempt: int, passed: bool, reason: str | None = None) -> None:
        self.patches.append(PatchCandidate(
            code=code, attempt=attempt, passed_validation=passed, rejection_reason=reason
        ))

    def finalize(self, fix: str | None = None, applied: bool = False) -> None:
        self.ended_at = time.time()
        self.final_fix = fix
        self.fix_applied = applied

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_seconds": self.duration_seconds,
            "target_file": self.target_file,
            "error_message": self.error_message,
            "root_cause_line": self.root_cause_line,
            "root_cause_file": self.root_cause_file,
            "severity": self.severity,
            "confidence": self.confidence,
            "fix_applied": self.fix_applied,
            "total_interactions": len(self.agent_interactions),
            "total_patches": len(self.patches),
            "metrics": self.metrics,
            "tags": self.tags,
            "interactions": [
                {
                    "agent": i.agent_name, "action": i.action,
                    "input": i.input_summary, "output": i.output_summary,
                    "duration_ms": i.duration_ms,
                }
                for i in self.agent_interactions
            ],
            "patches": [
                {
                    "attempt": p.attempt, "passed": p.passed_validation,
                    "reason": p.rejection_reason,
                }
                for p in self.patches
            ],
        }


class SessionRecorder:
    """Manages debugging session lifecycle and persistence."""

    def __init__(self, storage_dir: str | Path = "data/sessions"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._active_sessions: dict[str, DebugSession] = {}

    def start_session(self, target_file: str, error_message: str | None = None) -> DebugSession:
        session = DebugSession(target_file=target_file, error_message=error_message)
        self._active_sessions[session.session_id] = session
        return session

    def end_session(self, session_id: str, fix: str | None = None, applied: bool = False) -> DebugSession | None:
        session = self._active_sessions.pop(session_id, None)
        if session:
            session.finalize(fix=fix, applied=applied)
            self._persist(session)
        return session

    def get_session(self, session_id: str) -> DebugSession | None:
        if session_id in self._active_sessions:
            return self._active_sessions[session_id]
        return self._load(session_id)

    def list_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        """List recent sessions with summary info."""
        sessions: list[dict[str, Any]] = []

        # Active sessions
        for s in self._active_sessions.values():
            sessions.append({
                "session_id": s.session_id,
                "target_file": s.target_file,
                "started_at": s.started_at,
                "status": "active",
                "error": s.error_message,
            })

        # Persisted sessions
        if self.storage_dir.exists():
            files = sorted(self.storage_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
            for f in files[:limit]:
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    sessions.append({
                        "session_id": data.get("session_id", f.stem),
                        "target_file": data.get("target_file", ""),
                        "started_at": data.get("started_at", 0),
                        "status": "completed",
                        "error": data.get("error_message"),
                    })
                except (json.JSONDecodeError, OSError):
                    continue

        sessions.sort(key=lambda s: s.get("started_at", 0), reverse=True)
        return sessions[:limit]

    def _persist(self, session: DebugSession) -> None:
        filepath = self.storage_dir / f"{session.session_id}.json"
        filepath.write_text(
            json.dumps(session.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )

    def _load(self, session_id: str) -> DebugSession | None:
        filepath = self.storage_dir / f"{session_id}.json"
        if not filepath.exists():
            return None
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            session = DebugSession(
                session_id=data.get("session_id", session_id),
                started_at=data.get("started_at", 0),
                ended_at=data.get("ended_at"),
                target_file=data.get("target_file", ""),
                error_message=data.get("error_message"),
                severity=data.get("severity"),
                confidence=data.get("confidence"),
                metrics=data.get("metrics", {}),
                tags=data.get("tags", []),
            )
            return session
        except (json.JSONDecodeError, OSError):
            return None
