"""
message_bus — Inter-agent communication system.

Provides typed message passing between agents within a debugging session.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class AgentMessage:
    sender: str
    recipient: str  # agent name or "*" for broadcast
    msg_type: str  # "request", "response", "event", "control"
    payload: dict[str, Any] = field(default_factory=dict)
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    timestamp: float = field(default_factory=time.time)
    correlation_id: str | None = None  # links response to request


class MessageBus:
    """In-process message bus for agent communication."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[AgentMessage], Any]]] = defaultdict(list)
        self._history: list[AgentMessage] = []
        self._max_history = 500

    def subscribe(self, agent_name: str, handler: Callable[[AgentMessage], Any]) -> None:
        self._subscribers[agent_name].append(handler)

    def publish(self, message: AgentMessage) -> None:
        self._history.append(message)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        if message.recipient == "*":
            for name, handlers in self._subscribers.items():
                if name != message.sender:
                    for handler in handlers:
                        handler(message)
        elif message.recipient in self._subscribers:
            for handler in self._subscribers[message.recipient]:
                handler(message)

    def get_history(self, agent_name: str | None = None, limit: int = 50) -> list[AgentMessage]:
        if agent_name:
            msgs = [m for m in self._history if m.sender == agent_name or m.recipient == agent_name]
        else:
            msgs = list(self._history)
        return msgs[-limit:]

    def clear(self) -> None:
        self._history.clear()
