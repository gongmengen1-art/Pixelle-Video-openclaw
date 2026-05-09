# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""API endpoints for scripted asset editing demo pipeline."""

import os
from fastapi import APIRouter, HTTPException, Request
from loguru import logger

from api.dependencies import PixelleVideoDep
from api.schemas.video_edit import (
    ScriptedAssetEditRequest,
    ScriptedAssetEditResponse,
    ScriptedAssetEditAsyncResponse,
)
from api.routers.video import path_to_url
from api.tasks import task_manager, TaskType

router = APIRouter(prefix="/video/scripted-asset-edit", tags=["Video Edit Demo"])


def _probe_video_duration(video_path: str) -> float:
    """Best-effort final video duration probe used for API responses."""
    try:
        import ffmpeg
        probe = ffmpeg.probe(video_path)
        return float(probe["format"]["duration"])
    except Exception as e:
        logger.warning(f"Failed to probe video duration for {video_path}: {e}")
        return 0.0


async def _run_scripted_asset_edit(
    *,
    request_body: ScriptedAssetEditRequest,
    pixelle_video: PixelleVideoDep,
    request: Request,
    task_id: str | None = None,
) -> dict:
    """Run the scripted asset edit pipeline and normalize the API result."""

    progress_callback = None
    if task_id:
        def progress_callback(event):
            task_manager.update_progress(
                task_id=task_id,
                current=int(event.progress * 1000),
                total=1000,
                message=event.extra_info or event.event_type,
            )

    result_ctx = await pixelle_video.pipelines["scripted_asset_edit"](
        script_text=request_body.script_text,
        assets=request_body.asset_paths,
        project_name=request_body.project_name or "",
        split_mode=request_body.split_mode,
        duration_target=request_body.duration_target,
        editing_instruction=request_body.editing_instruction,
        source=request_body.source,
        bgm_path=request_body.bgm_path,
        bgm_volume=request_body.bgm_volume,
        bgm_mode=request_body.bgm_mode,
        subtitle_enabled=request_body.subtitle_enabled,
        pace=request_body.pace,
        transition_style=request_body.transition_style,
        allow_asset_reuse=request_body.allow_asset_reuse,
        skip_asset_analysis=request_body.skip_asset_analysis,
        frame_template=request_body.frame_template,
        tts_workflow=request_body.tts_workflow,
        ref_audio=request_body.ref_audio,
        voice_id=request_body.voice_id,
        tts_speed=request_body.tts_speed,
        progress_callback=progress_callback,
    )

    file_size = os.path.getsize(result_ctx.final_video_path) if os.path.exists(result_ctx.final_video_path) else 0
    video_url = path_to_url(request, str(result_ctx.final_video_path))
    duration = getattr(result_ctx.storyboard, "total_duration", 0.0) if getattr(result_ctx, "storyboard", None) else 0.0
    if not duration and result_ctx.final_video_path and os.path.exists(result_ctx.final_video_path):
        duration = _probe_video_duration(str(result_ctx.final_video_path))

    return {
        "video_url": video_url,
        "duration": duration,
        "file_size": file_size,
    }


@router.post("/sync", response_model=ScriptedAssetEditResponse)
async def generate_scripted_asset_edit_sync(
    request_body: ScriptedAssetEditRequest,
    pixelle_video: PixelleVideoDep,
    request: Request,
):
    """
    Generate a demo video from provided script + provided assets.

    This is the API counterpart of the assistant-driven editing workflow.
    """
    try:
        logger.info(f"Scripted asset edit sync: {request_body.project_name or request_body.script_text[:50]}...")

        result = await _run_scripted_asset_edit(
            request_body=request_body,
            pixelle_video=pixelle_video,
            request=request,
        )

        return ScriptedAssetEditResponse(
            **result,
        )
    except Exception as e:
        logger.error(f"Scripted asset edit sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/async", response_model=ScriptedAssetEditAsyncResponse)
async def generate_scripted_asset_edit_async(
    request_body: ScriptedAssetEditRequest,
    pixelle_video: PixelleVideoDep,
    request: Request,
):
    """
    Generate a demo video asynchronously from provided script + assets.

    This is the final task-loop hop for chat/skill integrations: callers get a
    task_id immediately, then poll `/api/tasks/{task_id}` until completion.
    """
    try:
        logger.info(f"Scripted asset edit async: {request_body.project_name or request_body.script_text[:50]}...")

        task = task_manager.create_task(
            task_type=TaskType.VIDEO_EDIT,
            request_params=request_body.model_dump(),
        )

        async def execute_scripted_asset_edit():
            return await _run_scripted_asset_edit(
                request_body=request_body,
                pixelle_video=pixelle_video,
                request=request,
                task_id=task.task_id,
            )

        await task_manager.execute_task(
            task_id=task.task_id,
            coro_func=execute_scripted_asset_edit,
        )

        return ScriptedAssetEditAsyncResponse(task_id=task.task_id)
    except Exception as e:
        logger.error(f"Scripted asset edit async error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
