"""
graph_serializer — Converts internal graph structures into frontend-ready
JSON for ReactFlow and D3.js rendering.
"""

from __future__ import annotations

from typing import Any


class GraphSerializer:
    """Serializes call graphs, CFGs, dependency graphs, and execution traces
    into frontend-consumable JSON structures."""

    # --- Call Graph → ReactFlow ---

    @staticmethod
    def call_graph_to_reactflow(call_graph_dict: dict[str, Any]) -> dict[str, Any]:
        """Convert call graph to ReactFlow nodes and edges."""
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        node_set: set[str] = set()

        for i, node_id in enumerate(call_graph_dict.get("nodes", [])):
            label = node_id.split(".")[-1] if "." in node_id else node_id
            nodes.append({
                "id": node_id,
                "data": {"label": label, "fullName": node_id},
                "position": {"x": (i % 6) * 200, "y": (i // 6) * 120},
                "type": "default",
            })
            node_set.add(node_id)

        for i, edge in enumerate(call_graph_dict.get("edges", [])):
            source = edge.get("caller", "")
            target = edge.get("callee", "")
            if source in node_set and target in node_set:
                edges.append({
                    "id": f"e{i}",
                    "source": source,
                    "target": target,
                    "animated": edge.get("resolved", True),
                    "label": f"L{edge.get('line', '')}",
                    "style": {"stroke": "#a855f7" if edge.get("resolved") else "#ef4444"},
                })

        return {"nodes": nodes, "edges": edges, "type": "call_graph"}

    # --- CFG → ReactFlow ---

    @staticmethod
    def cfg_to_reactflow(cfg_dict: dict[str, Any]) -> dict[str, Any]:
        """Convert control flow graph to ReactFlow nodes and edges."""
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        blocks = cfg_dict.get("blocks", {})
        for bid_str, block in blocks.items():
            bid = str(bid_str)
            label = block.get("label", f"B{bid}")
            stmts = block.get("statements", [])
            stmt_text = "\n".join(f"L{s[0]}: {s[1]}" for s in stmts) if stmts else label

            nodes.append({
                "id": bid,
                "data": {"label": label, "statements": stmt_text, "start_line": block.get("start_line"), "end_line": block.get("end_line")},
                "position": {"x": 150, "y": int(bid) * 140},
                "type": "default",
                "style": _cfg_block_style(label),
            })

        for i, edge in enumerate(cfg_dict.get("edges", [])):
            label = edge.get("label", "")
            edges.append({
                "id": f"e{i}",
                "source": str(edge.get("source", "")),
                "target": str(edge.get("target", "")),
                "label": label,
                "animated": label in ("true", "except", "loop_back"),
                "style": {"stroke": _cfg_edge_color(label)},
            })

        return {"nodes": nodes, "edges": edges, "type": "cfg", "function": cfg_dict.get("function", "")}

    # --- Dependency Graph → ReactFlow ---

    @staticmethod
    def dependency_graph_to_reactflow(dep_dict: dict[str, Any]) -> dict[str, Any]:
        """Convert dependency graph to ReactFlow nodes and edges."""
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        node_ids = dep_dict.get("nodes", [])

        for i, node_path in enumerate(node_ids):
            import os
            label = os.path.basename(node_path)
            nodes.append({
                "id": node_path,
                "data": {"label": label, "fullPath": node_path},
                "position": {"x": (i % 5) * 220, "y": (i // 5) * 100},
                "type": "default",
            })

        for i, edge in enumerate(dep_dict.get("edges", [])):
            edges.append({
                "id": f"e{i}",
                "source": edge.get("source", ""),
                "target": edge.get("target", ""),
                "label": edge.get("import", ""),
                "style": {"stroke": "#3b82f6"},
            })

        cycles = dep_dict.get("cycles", [])
        return {"nodes": nodes, "edges": edges, "type": "dependency_graph", "cycles": cycles}

    # --- Execution Timeline ---

    @staticmethod
    def trace_to_timeline(trace_dict: dict[str, Any]) -> dict[str, Any]:
        """Convert execution trace to a timeline visualization format."""
        events = trace_dict.get("events", [])
        timeline_entries: list[dict[str, Any]] = []

        for i, ev in enumerate(events[:500]):  # Cap at 500 for rendering
            entry = {
                "index": i,
                "type": ev.get("type", ""),
                "line": ev.get("line", 0),
                "function": ev.get("function", ""),
                "depth": ev.get("depth", 0),
                "file": ev.get("file", ""),
            }
            if ev.get("exception"):
                entry["exception"] = ev["exception"]
            if ev.get("type") == "return":
                entry["return_value"] = ev.get("return", "")
            timeline_entries.append(entry)

        return {
            "type": "execution_timeline",
            "total_events": trace_dict.get("total_events", len(events)),
            "displayed_events": len(timeline_entries),
            "max_depth": trace_dict.get("max_depth", 0),
            "entries": timeline_entries,
        }

    # --- Variable Evolution ---

    @staticmethod
    def variable_history_to_chart(history: list[dict[str, Any]], var_name: str) -> dict[str, Any]:
        """Convert variable history to a chart-friendly format."""
        return {
            "type": "variable_evolution",
            "variable": var_name,
            "data_points": [
                {
                    "x": h.get("event_index", i),
                    "y_label": h.get("value", ""),
                    "line": h.get("lineno", 0),
                    "function": h.get("function", ""),
                }
                for i, h in enumerate(history)
            ],
        }

    # --- Profiling Heatmap ---

    @staticmethod
    def profiling_to_heatmap(profiling_dict: dict[str, Any]) -> dict[str, Any]:
        """Convert profiling report to heatmap data."""
        functions = profiling_dict.get("functions", [])
        total_time = profiling_dict.get("total_time", 1)

        heatmap_data = []
        for func in functions[:30]:
            pct = (func.get("cumulative_time", 0) / max(total_time, 0.001)) * 100
            heatmap_data.append({
                "name": func.get("name", ""),
                "file": func.get("file", ""),
                "line": func.get("line", 0),
                "time_pct": round(pct, 1),
                "calls": func.get("calls", 0),
                "intensity": min(1.0, pct / 50),  # 0–1 scale for color mapping
            })

        return {"type": "profiling_heatmap", "data": heatmap_data}


def _cfg_block_style(label: str) -> dict[str, str]:
    color_map = {
        "entry": "#10b981",
        "exit": "#ef4444",
        "if_true": "#3b82f6",
        "if_false": "#f59e0b",
        "loop_body": "#8b5cf6",
        "except": "#ef4444",
        "finally": "#6366f1",
    }
    for key, color in color_map.items():
        if key in label:
            return {"borderColor": color, "borderWidth": "2px"}
    return {}


def _cfg_edge_color(label: str) -> str:
    colors = {
        "true": "#10b981",
        "false": "#ef4444",
        "except": "#f59e0b",
        "finally": "#6366f1",
        "loop_back": "#8b5cf6",
        "return": "#ef4444",
    }
    return colors.get(label, "#64748b")
