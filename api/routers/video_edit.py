# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""API endpoints for scripted asset editing demo pipeline."""

import os
import ffmpeg
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
            cover_enabled=request_body.cover_enabled,
            cover_title=request_body.cover_title,
            cover_ref_image=request_body.cover_ref_image,
            subtitle_color=request_body.subtitle_color,
            subtitle_font_size=request_body.subtitle_font_size,
            subtitle_max_chars=request_body.subtitle_max_chars,
        )

        file_size = os.path.getsize(result_ctx.final_video_path) if os.path.exists(result_ctx.final_video_path) else 0
        video_url = path_to_url(request, result_ctx.final_video_path)
        duration = 0.0
        try:
            if os.path.exists(result_ctx.final_video_path):
                probe = ffmpeg.probe(result_ctx.final_video_path)
                duration = float(probe['format']['duration'])
        except Exception:
            duration = getattr(result_ctx.storyboard, "total_duration", 0.0) if getattr(result_ctx, "storyboard", None) else 0.0

        cover_image_url = None
        cover_path = getattr(result_ctx, 'cover_image_path', None)
        if cover_path and os.path.exists(cover_path):
            cover_image_url = path_to_url(request, cover_path)

        return ScriptedAssetEditResponse(
            video_url=video_url,
            cover_image_url=cover_image_url,
            duration=duration,
            file_size=file_size,
        )
    except Exception as e:
        logger.error(f"Scripted asset edit sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/async", response_model=ScriptedAssetEditAsyncResponse)
async def generate_scripted_asset_edit_async(
    request_body: ScriptedAssetEditRequest,
    pixelle_video: PixelleVideoDep,
):
    """
    Start scripted asset edit asynchronously.

    Returns a task_id immediately.  Poll GET /api/tasks/{task_id} to track progress.
    When status == "completed", the task result contains:
      video_path, cover_image_path, duration, file_size (raw paths for local use).

    Progress is exposed as task.progress.percentage (0–100).
    """
    try:
        logger.info(f"Scripted asset edit async: {request_body.project_name or request_body.script_text[:50]}...")

        task = task_manager.create_task(
            task_type=TaskType.VIDEO_GENERATION,
            request_params={"project_name": request_body.project_name, "script_length": len(request_body.script_text)},
        )
        task_id = task.task_id

        async def _run_pipeline():
            from pixelle_video.models.progress import ProgressEvent

            def _on_progress(event: ProgressEvent):
                pct = int(event.progress * 100)
                frame_info = ""
                if event.frame_current and event.frame_total:
                    frame_info = f"帧 {event.frame_current}/{event.frame_total}"
                action_map = {
                    "audio": "生成配音",
                    "media": "生成画面",
                    "compose": "合成画面",
                    "video": "合成视频",
                    "subtitle": "添加字幕",
                }
                action_label = action_map.get(event.action or "", event.action or "处理中")
                msg = f"{frame_info} - {action_label}" if frame_info else action_label
                task_manager.update_progress(task_id=task_id, current=pct, total=100, message=msg)

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
                cover_enabled=request_body.cover_enabled,
                cover_title=request_body.cover_title,
                cover_ref_image=request_body.cover_ref_image,
                subtitle_color=request_body.subtitle_color,
                subtitle_font_size=request_body.subtitle_font_size,
                subtitle_max_chars=request_body.subtitle_max_chars,
                progress_callback=_on_progress,
            )

            duration = 0.0
            final_path = result_ctx.final_video_path or ""
            file_size = os.path.getsize(final_path) if final_path and os.path.exists(final_path) else 0
            try:
                if final_path and os.path.exists(final_path):
                    probe = ffmpeg.probe(final_path)
                    duration = float(probe["format"]["duration"])
            except Exception:
                pass

            task_manager.update_progress(task_id=task_id, current=100, total=100, message="生成完成")
            return {
                "video_path":        final_path,
                "cover_image_path":  getattr(result_ctx, "cover_image_path", None),
                "duration":          duration,
                "file_size":         file_size,
            }

        await task_manager.execute_task(task_id, _run_pipeline)
        return ScriptedAssetEditAsyncResponse(task_id=task_id)

    except Exception as e:
        logger.error(f"Scripted asset edit async error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
