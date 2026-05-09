# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Scripted Asset Edit Pipeline

A pipeline specialized for assistant-driven video editing demos where:
- script is provided by the user
- media assets are provided by the user
- TTS / voice clone / BGM / editing instructions are collected interactively

This pipeline is intentionally built on top of the existing AssetBasedPipeline
so we can reuse most of Pixelle-Video's production stack while changing the
front-end semantics from "generate a marketing video from intent" to
"edit a demo video from provided script + provided assets".
"""

from pathlib import Path
from typing import Any, Optional, Callable
import subprocess

from loguru import logger
from pydantic import BaseModel, Field

from pixelle_video.pipelines.asset_based import AssetBasedPipeline
from pixelle_video.models.progress import ProgressEvent

ProgressCallback = Optional[Callable[[ProgressEvent], None]]


class ScriptedScene(BaseModel):
    """A single edited scene mapped from provided script."""

    scene_number: int = Field(description="Scene number starting from 1")
    script_segment: str = Field(description="Original user-provided script segment")
    asset_path: str = Field(description="Matched asset path")
    narrations: list[str] = Field(description="Narration lines for this scene")
    duration: int = Field(description="Estimated duration in seconds")
    transition: Optional[str] = Field(default=None, description="Transition hint")
    emphasis: Optional[str] = Field(default=None, description="Emphasis / hook / CTA hint")


class ScriptedEditPlan(BaseModel):
    """Structured scene plan for scripted asset editing."""

    scenes: list[ScriptedScene] = Field(description="Ordered scene plan")


class ScriptedAssetEditPipeline(AssetBasedPipeline):
    """
    Pipeline for demo-style automated video editing.

    Key differences from AssetBasedPipeline:
    1. The script is provided directly by the user
    2. The pipeline matches provided script segments to provided assets
    3. Editing instructions are accepted as first-class input
    4. Future extension point for subtitle/pace/transition rules
    """

    async def __call__(
        self,
        script_text: str,
        assets: list[str],
        project_name: str = "",
        split_mode: str = "paragraph",
        duration_target: int = 30,
        editing_instruction: Optional[str] = None,
        source: str = "runninghub",
        bgm_path: Optional[str] = None,
        bgm_volume: float = 0.2,
        bgm_mode: str = "loop",
        subtitle_enabled: bool = True,
        pace: str = "medium",
        transition_style: str = "simple",
        allow_asset_reuse: bool = True,
        progress_callback: ProgressCallback = None,
        **kwargs,
    ):
        """
        Execute scripted asset editing pipeline.
        """
        from pixelle_video.pipelines.linear import PipelineContext

        self._progress_callback = progress_callback

        ctx = PipelineContext(
            input_text=script_text,
            params={
                "script_text": script_text,
                "assets": assets,
                "project_name": project_name,
                "video_title": project_name,
                "intent": editing_instruction or project_name or "scripted asset edit",
                "split_mode": split_mode,
                "duration": duration_target,
                "editing_instruction": editing_instruction,
                "source": source,
                "bgm_path": bgm_path,
                "bgm_volume": bgm_volume,
                "bgm_mode": bgm_mode,
                "subtitle_enabled": subtitle_enabled,
                "pace": pace,
                "transition_style": transition_style,
                "allow_asset_reuse": allow_asset_reuse,
                **kwargs,
            },
        )
        ctx.request = ctx.params

        try:
            await self.setup_environment(ctx)
            await self.determine_title(ctx)
            await self.generate_content(ctx)
            await self.plan_visuals(ctx)
            await self.apply_editing_rules(ctx)
            await self.initialize_storyboard(ctx)
            await self.produce_assets(ctx)
            await self.post_production(ctx)
            await self.finalize(ctx)
            return ctx
        except Exception as e:
            await self.handle_exception(ctx, e)
            raise

    async def setup_environment(self, context):
        """
        Setup task environment.

        If skip_asset_analysis=True, build a minimal asset index directly from
        provided files and avoid ComfyUI/RunningHub dependency for the first MVP.
        Otherwise fall back to AssetBasedPipeline.setup_environment().
        """
        skip_asset_analysis = context.request.get("skip_asset_analysis", True)
        if not skip_asset_analysis:
            logger.info("🔍 Full asset analysis enabled for scripted asset edit pipeline")
            return await super().setup_environment(context)

        from pixelle_video.utils.os_util import create_task_output_dir, get_task_final_video_path

        task_dir, task_id = create_task_output_dir()
        context.task_id = task_id
        context.task_dir = Path(task_dir)
        context.final_video_path = get_task_final_video_path(task_id)

        logger.info(f"📁 Task directory created: {task_dir}")
        logger.info("⚡ Skipping asset semantic analysis, building minimal asset index...")

        assets: list[str] = context.request.get("assets", [])
        if not assets:
            raise ValueError("No assets provided. Please upload at least one image or video.")

        self.asset_index = {}
        total_assets = len(assets)
        self._emit_progress(ProgressEvent(
            event_type="analyzing_assets",
            progress=0.01,
            frame_current=0,
            frame_total=total_assets,
            extra_info="start"
        ))

        for i, asset_path in enumerate(assets, 1):
            asset_path_obj = Path(asset_path)
            if not asset_path_obj.exists():
                logger.warning(f"Asset not found: {asset_path}")
                continue

            asset_type = self._get_asset_type(asset_path_obj)
            if asset_type == "unknown":
                logger.warning(f"Unknown asset type skipped: {asset_path}")
                continue

            progress = 0.01 + (i - 1) / total_assets * 0.14
            self._emit_progress(ProgressEvent(
                event_type="analyzing_asset",
                progress=progress,
                frame_current=i,
                frame_total=total_assets,
                extra_info=asset_path_obj.name
            ))

            self.asset_index[asset_path] = {
                "path": asset_path,
                "type": asset_type,
                "name": asset_path_obj.name,
                "description": f"User provided {asset_type} asset: {asset_path_obj.name}",
            }

        if not self.asset_index:
            raise ValueError("No valid assets available after minimal asset indexing")

        context.asset_index = self.asset_index
        logger.success(f"✅ Minimal asset index ready: {len(self.asset_index)} assets")
        self._emit_progress(ProgressEvent(
            event_type="analyzing_assets",
            progress=0.15,
            frame_current=len(self.asset_index),
            frame_total=total_assets,
            extra_info="complete"
        ))
        return context

    async def determine_title(self, context):
        title = context.request.get("project_name") or context.request.get("video_title")
        if title:
            context.title = title
            logger.info(f"📝 Project title: {title} (user-specified)")
        else:
            context.title = ""
            logger.info("📝 No project title specified")
        return context

    async def generate_content(self, context):
        """
        Convert provided script into structured scenes and match them to assets.

        Current skeleton behavior:
        - split script by paragraphs / lines / sentences
        - map segments to assets in order (cyclic if allow_asset_reuse)

        Future behavior:
        - use LLM + asset descriptions + editing instruction to produce a richer
          scene plan with better scene/asset matching.
        """
        from pixelle_video.utils.content_generators import split_narration_script

        logger.info("🧠 Building scripted edit plan from provided script...")
        self._emit_progress(ProgressEvent(event_type="generating_script", progress=0.16))

        script_text = context.request.get("script_text", context.input_text)
        split_mode = context.request.get("split_mode", "paragraph")
        allow_asset_reuse = context.request.get("allow_asset_reuse", True)

        segments = await split_narration_script(script_text, split_mode=split_mode)
        segments = [seg.strip() for seg in segments if seg and seg.strip()]
        if not segments:
            raise ValueError("No valid script segments produced from provided script_text")

        asset_paths = list(self.asset_index.keys())
        if not asset_paths:
            raise ValueError("No analyzed assets available for scripted edit pipeline")

        # For user-provided asset editing, coverage is more important than
        # strictly following the script split. If a short script is provided
        # with multiple assets, create at least one scene per asset so every
        # video/photo makes it into the final cut.
        if len(segments) < len(asset_paths):
            segments = self._expand_segments_to_cover_assets(
                segments=segments,
                asset_paths=asset_paths,
                editing_instruction=context.request.get("editing_instruction"),
            )

        scenes = []
        for idx, segment in enumerate(segments, start=1):
            if idx - 1 < len(asset_paths):
                asset_path = asset_paths[idx - 1]
            elif allow_asset_reuse:
                asset_path = asset_paths[(idx - 1) % len(asset_paths)]
            else:
                asset_path = asset_paths[-1]

            asset_metadata = self.asset_index.get(asset_path, {})
            asset_duration = self._get_asset_duration(asset_path) if asset_metadata.get("type") == "video" else 0.0
            estimated_script_duration = max(2, min(8, len(segment) // 12 or 3))

            scenes.append(
                {
                    "scene_number": idx,
                    "script_segment": segment,
                    "asset_path": asset_path,
                    "narrations": [segment],
                    # Duration is a floor, not a crop target: for video assets
                    # we preserve at least the original material length.
                    "duration": max(estimated_script_duration, int(asset_duration + 0.999)),
                    "transition": context.request.get("transition_style", "simple"),
                    "emphasis": None,
                }
            )

        plan = ScriptedEditPlan(scenes=[ScriptedScene(**scene) for scene in scenes])
        context.script = [scene.model_dump() for scene in plan.scenes]

        logger.success(f"✅ Built scripted edit plan with {len(context.script)} scenes")
        self._emit_progress(ProgressEvent(event_type="generating_script", progress=0.25, extra_info="complete"))
        return context

    async def plan_visuals(self, context):
        logger.info("🎯 Preparing scripted scene-asset mapping...")
        context.matched_scenes = [
            {
                **scene,
                "matched_asset": scene["asset_path"],
            }
            for scene in context.script
        ]
        return context

    async def apply_editing_rules(self, context):
        """
        Normalize editing instruction into simple per-scene metadata.

        Current skeleton:
        - stores global editing settings onto context for downstream use
        - leaves room for future conversion into template_params / subtitle rules /
          transition timing / hook & CTA insertion.
        """
        logger.info("🎬 Applying editing rules (skeleton)...")
        context.editing_rules = {
            "subtitle_enabled": context.request.get("subtitle_enabled", True),
            "pace": context.request.get("pace", "medium"),
            "transition_style": context.request.get("transition_style", "simple"),
            "editing_instruction": context.request.get("editing_instruction"),
        }
        return context

    async def initialize_storyboard(self, context):
        await super().initialize_storyboard(context)

        # Inject optional template params / editing metadata for future use.
        if getattr(context, "editing_rules", None):
            context.config.template_params = {
                **(context.config.template_params or {}),
                "subtitle_enabled": context.editing_rules.get("subtitle_enabled", True),
                "pace": context.editing_rules.get("pace", "medium"),
                "transition_style": context.editing_rules.get("transition_style", "simple"),
            }

        # Ensure narration aligns with script_segment semantics.
        for frame, scene in zip(context.storyboard.frames, context.matched_scenes):
            frame.narration = " ".join(scene.get("narrations", []))
            asset_path = scene.get("matched_asset") or scene.get("asset_path")
            asset_metadata = self.asset_index.get(asset_path, {})
            if asset_metadata.get("type") == "video":
                # Downstream merge must not trim user videos to narration length.
                frame.preserve_video_duration = True

        return context

    def _expand_segments_to_cover_assets(
        self,
        *,
        segments: list[str],
        asset_paths: list[str],
        editing_instruction: Optional[str] = None,
    ) -> list[str]:
        """Ensure every provided asset receives a scene, allowing copy tweaks."""
        if not segments:
            segments = ["画面自然展开，营造舒缓、宁静的观看氛围。"]

        expanded = list(segments)
        while len(expanded) < len(asset_paths):
            asset_name = Path(asset_paths[len(expanded)]).stem
            if editing_instruction:
                expanded.append(f"随后镜头自然过渡，继续呈现{asset_name}的细节，让画面保持连贯舒缓。")
            else:
                expanded.append(f"随后镜头自然过渡，继续呈现{asset_name}的细节，与前一幕形成安静连贯的呼应。")
        return expanded

    def _get_asset_duration(self, asset_path: str) -> float:
        """Return media duration in seconds; 0 for unknown/non-video files."""
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    asset_path,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return max(0.0, float(result.stdout.strip()))
        except Exception as e:
            logger.warning(f"Failed to probe asset duration for {asset_path}: {e}")
            return 0.0
