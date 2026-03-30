"""
Patch System API — Safe Git-based patch generation and application.

Routes:
  POST /patch/generate  — Generate unified diff between original file and fixed code
  POST /patch/apply     — Apply fix safely (Git workflow preferred, fallback available)
  POST /patch/preview   — Structured before/after diff for frontend DiffViewer
"""

from fastapi import APIRouter, HTTPException

from backend.schemas import (
    GeneratePatchRequest, GeneratePatchResponse,
    ApplyPatchRequest, ApplyPatchResponse,
    PatchPreviewRequest,
)
from backend.utils import _safe_resolve_workspace_path
from backend.services.patch_service import (
    generate_patch, generate_preview, apply_patch_smart, GIT_AVAILABLE,
)
from backend.config import logger

router = APIRouter(prefix="/patch", tags=["patch"])


@router.post("/generate", response_model=GeneratePatchResponse)
async def generate_patch_endpoint(request: GeneratePatchRequest):
    """
    Generate a unified diff patch between the original file content
    and the proposed fixed code.

    Returns:
        Patch string in unified diff format with statistics.
    """
    file_path = _safe_resolve_workspace_path(
        request.file_path, must_exist=True, enforce_python=True
    )

    try:
        result = generate_patch(file_path, request.fixed_code)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Patch generation failed for %s", file_path)
        raise HTTPException(status_code=500, detail=f"Patch generation failed: {exc}") from exc

    return GeneratePatchResponse(
        patch=result.patch,
        file_path=result.file_path,
        original_lines=result.original_lines,
        fixed_lines=result.fixed_lines,
        additions=result.additions,
        deletions=result.deletions,
    )


@router.post("/apply", response_model=ApplyPatchResponse)
async def apply_patch_endpoint(request: ApplyPatchRequest):
    """
    Apply a fix to a file safely.

    Strategy (in order of preference):
      1. Git workflow — creates ai-fix/<timestamp> branch, commits fix
      2. Unified patch — applies diff hunks if patch_content is provided
      3. Direct write — writes fixed code with .bak backup

    The Git workflow stashes uncommitted changes before operating
    and restores them after. On failure, it rolls back to the
    original branch.
    """
    file_path = _safe_resolve_workspace_path(
        request.file_path, must_exist=True, enforce_python=True
    )

    try:
        result = apply_patch_smart(
            file_path,
            request.fixed_code,
            patch_content=request.patch_content,
            use_git=request.use_git,
        )
    except Exception as exc:
        logger.exception("Patch application failed for %s", file_path)
        raise HTTPException(status_code=500, detail=f"Patch application failed: {exc}") from exc

    if not result.success:
        # Return 409 Conflict if the patch couldn't be applied
        return ApplyPatchResponse(
            success=False,
            method=result.method,
            file_path=result.file_path,
            message=result.message,
            conflict=result.conflict,
            stash_restored=result.stash_restored,
        )

    return ApplyPatchResponse(
        success=True,
        method=result.method,
        file_path=result.file_path,
        message=result.message,
        branch_name=result.branch_name,
        commit_sha=result.commit_sha,
        stash_restored=result.stash_restored,
    )


@router.post("/preview")
async def preview_patch_endpoint(request: PatchPreviewRequest):
    """
    Generate a structured before/after diff for the frontend DiffViewer.

    Returns hunk-level diff data with line numbers and change types,
    suitable for rendering a side-by-side or unified diff view.
    """
    file_path = _safe_resolve_workspace_path(
        request.file_path, must_exist=True, enforce_python=True
    )

    try:
        preview = generate_preview(file_path, request.fixed_code)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Preview generation failed for %s", file_path)
        raise HTTPException(status_code=500, detail=f"Preview generation failed: {exc}") from exc

    return {
        "file_path": preview.file_path,
        "original_code": preview.original_code,
        "fixed_code": preview.fixed_code,
        "hunks": preview.hunks,
        "stats": preview.stats,
        "git_available": GIT_AVAILABLE,
    }
