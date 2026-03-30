"""
visualization — FastAPI router for graph data serving.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

router = APIRouter(tags=["visualization"])


class GraphRequest(BaseModel):
    workspace_root: str


@router.post("/dependency_graph")
async def dependency_graph(req: GraphRequest):
    """Build and return the dependency graph for ReactFlow visualization."""
    try:
        from core_engine import WorkspaceIndexer
        from visualization_engine import GraphSerializer
        indexer = WorkspaceIndexer(req.workspace_root, build_cfgs=False)
        idx = indexer.index()
        if idx.dependency_graph:
            return GraphSerializer.dependency_graph_to_reactflow(idx.dependency_graph.to_dict())
        return {"nodes": [], "edges": [], "type": "dependency_graph"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/call_graph")
async def call_graph(req: GraphRequest):
    """Build and return the call graph for ReactFlow visualization."""
    try:
        from core_engine import WorkspaceIndexer
        from visualization_engine import GraphSerializer
        indexer = WorkspaceIndexer(req.workspace_root, build_cfgs=False)
        idx = indexer.index()
        if idx.call_graph:
            return GraphSerializer.call_graph_to_reactflow(idx.call_graph.to_dict())
        return {"nodes": [], "edges": [], "type": "call_graph"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/cfg/{filename}")
async def control_flow_graph(filename: str, workspace_root: str = Query(...)):
    """Build CFGs for all functions in a specific file."""
    try:
        from core_engine import CFGBuilder
        from visualization_engine import GraphSerializer
        filepath = Path(workspace_root) / filename
        if not filepath.exists():
            raise HTTPException(status_code=404, detail="File not found")
        source = filepath.read_text(encoding="utf-8", errors="replace")
        builder = CFGBuilder()
        cfgs = builder.build_for_source(source)
        return [GraphSerializer.cfg_to_reactflow(cfg.to_dict()) for cfg in cfgs]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/project_index")
async def project_index(req: GraphRequest):
    """Return the full project index summary."""
    try:
        from core_engine import WorkspaceIndexer
        indexer = WorkspaceIndexer(req.workspace_root)
        idx = indexer.index()
        return idx.summary()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
