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
)
from api.routers.video import path_to_url

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
        )

        file_size = os.path.getsize(result_ctx.final_video_path) if os.path.exists(result_ctx.final_video_path) else 0
        video_url = path_to_url(request, result_ctx.final_video_path)
        duration = getattr(result_ctx.storyboard, "total_duration", 0.0) if getattr(result_ctx, "storyboard", None) else 0.0

        return ScriptedAssetEditResponse(
            video_url=video_url,
            duration=duration,
            file_size=file_size,
        )
    except Exception as e:
        logger.error(f"Scripted asset edit sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
