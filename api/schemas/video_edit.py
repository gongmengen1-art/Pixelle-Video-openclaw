# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Schemas for scripted asset video editing demo."""

from typing import Optional, Literal
from pydantic import BaseModel, Field


class ScriptedAssetEditRequest(BaseModel):
    """Request payload for scripted asset edit demo."""

    script_text: str = Field(..., description="User-provided script text")
    asset_paths: list[str] = Field(..., description="Paths to image/video assets")
    project_name: Optional[str] = Field(None, description="Optional project / video title")
    split_mode: Literal["paragraph", "line", "sentence"] = Field(
        "paragraph", description="How to split provided script into scenes"
    )
    duration_target: int = Field(30, ge=5, le=600, description="Target video duration in seconds")

    tts_workflow: Optional[str] = Field(None, description="TTS workflow key")
    ref_audio: Optional[str] = Field(None, description="Reference audio path for voice cloning")
    voice_id: Optional[str] = Field(None, description="Legacy voice ID")
    tts_speed: float = Field(1.0, ge=0.5, le=2.0, description="TTS speed")

    subtitle_enabled: bool = Field(True, description="Whether subtitles should be enabled")
    bgm_path: Optional[str] = Field(None, description="Background music path")
    bgm_volume: float = Field(0.2, ge=0.0, le=1.0, description="BGM volume")
    bgm_mode: Literal["loop", "once"] = Field("loop", description="BGM playback mode")

    pace: Literal["slow", "medium", "fast"] = Field("medium", description="Editing pace")
    transition_style: Literal["none", "simple", "dynamic"] = Field(
        "simple", description="Scene transition style"
    )
    editing_instruction: Optional[str] = Field(
        None,
        description="Natural language editing note, e.g. hook / CTA / emphasis / tone"
    )
    allow_asset_reuse: bool = Field(True, description="Allow asset reuse when segments exceed asset count")
    skip_asset_analysis: bool = Field(
        True,
        description="Skip image/video semantic analysis and build a minimal asset index directly from provided files"
    )
    source: Literal["runninghub", "selfhost"] = Field("runninghub", description="Media analysis/generation source")
    frame_template: str = Field(
        "1080x1920/asset_default.html",
        description="Template used for final frame composition"
    )


class ScriptedAssetEditResponse(BaseModel):
    success: bool = True
    message: str = "Success"
    video_url: str
    duration: float
    file_size: int


class ScriptedAssetEditAsyncResponse(BaseModel):
    success: bool = True
    message: str = "Task created successfully"
    task_id: str
