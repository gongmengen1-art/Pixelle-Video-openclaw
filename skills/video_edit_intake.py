from __future__ import annotations

from copy import deepcopy
from typing import Any

DEFAULT_REQUEST_DRAFT: dict[str, Any] = {
    "project_name": "",
    "script_text": "",
    "asset_paths": [],
    "split_mode": "paragraph",
    "duration_target": 30,
    "skip_asset_analysis": True,
    "tts_workflow": None,
    "ref_audio": None,
    "voice_id": "zh-CN-YunjianNeural",
    "tts_speed": 1.0,
    "subtitle_enabled": True,
    "bgm_path": None,
    "bgm_volume": 0.2,
    "bgm_mode": "loop",
    "pace": "medium",
    "transition_style": "simple",
    "editing_instruction": None,
    "allow_asset_reuse": True,
    "source": "selfhost",
    "frame_template": "1080x1920/asset_default.html",
}

REQUIRED_FIELDS = ["script_text", "asset_paths", "frame_template"]

FIELD_PROMPTS: dict[str, str] = {
    "script_text": "请把完整文案直接发我，我会按段落或句子帮你拆成视频场景。",
    "asset_paths": "请把要参与剪辑的图片或视频素材发我；如果是多个文件，我会按顺序或后续规则匹配到文案场景。",
    "frame_template": "你要竖屏、横屏还是方形？如果你不指定，我默认先用竖屏 9:16 模板。",
    "tts_workflow": "你要用默认音色，还是指定一个 TTS 工作流？",
    "ref_audio": "如果你想做声音克隆，请发一段 mp3/wav 参考音频。",
    "bgm_path": "如果你要背景音乐，请发一个音频文件，或者告诉我直接用默认 BGM。",
    "editing_instruction": "如果你对节奏、转场、重点表达有要求，可以直接告诉我，比如“前3秒抓人，结尾落品牌”。",
}

FRAME_TEMPLATE_BY_RATIO = {
    "9:16": "1080x1920/asset_default.html",
    "16:9": "1920x1080/image_full.html",
    "1:1": "1080x1080/image_minimal_framed.html",
}


class IntakeState:
    """Mutable draft state for the video edit assistant."""

    def __init__(self, draft: dict[str, Any] | None = None):
        self.data: dict[str, Any] = deepcopy(DEFAULT_REQUEST_DRAFT)
        if draft:
            self.merge(draft)

    def merge(self, patch: dict[str, Any]) -> dict[str, Any]:
        """Merge a partial user-provided patch into the draft."""
        for key, value in patch.items():
            if key not in self.data:
                continue
            if value is None:
                continue
            if key == "asset_paths":
                if isinstance(value, list):
                    cleaned = [str(v).strip() for v in value if str(v).strip()]
                    if cleaned:
                        self.data[key] = cleaned
                elif isinstance(value, str) and value.strip():
                    self.data[key] = [value.strip()]
                continue
            if isinstance(value, str):
                value = value.strip()
                if value == "":
                    continue
            self.data[key] = value
        return self.data

    def apply_aspect_ratio(self, ratio: str | None) -> str | None:
        """Map a simple aspect ratio value into a frame template."""
        if not ratio:
            return None
        ratio = ratio.strip()
        template = FRAME_TEMPLATE_BY_RATIO.get(ratio)
        if template:
            self.data["frame_template"] = template
        return template

    def missing_required_fields(self) -> list[str]:
        missing = []
        for field in REQUIRED_FIELDS:
            value = self.data.get(field)
            if value is None:
                missing.append(field)
            elif isinstance(value, str) and not value.strip():
                missing.append(field)
            elif isinstance(value, list) and len(value) == 0:
                missing.append(field)
        return missing

    def missing_recommended_fields(self) -> list[str]:
        missing = []
        recommended = ["tts_workflow", "ref_audio", "bgm_path", "editing_instruction"]
        for field in recommended:
            value = self.data.get(field)
            if value is None:
                missing.append(field)
            elif isinstance(value, str) and not value.strip():
                missing.append(field)
        return missing

    def next_questions(self, limit: int = 3) -> list[dict[str, str]]:
        """Return the next most important missing-field prompts."""
        fields = self.missing_required_fields()
        if len(fields) < limit:
            for field in self.missing_recommended_fields():
                if field not in fields:
                    fields.append(field)
                if len(fields) >= limit:
                    break
        return [
            {"field": field, "prompt": FIELD_PROMPTS.get(field, f"请补充字段：{field}")}
            for field in fields[:limit]
        ]

    def ready(self) -> bool:
        return len(self.missing_required_fields()) == 0

    def build_api_payload(self) -> dict[str, Any]:
        """Build a clean request payload for /api/video/scripted-asset-edit/sync."""
        payload = deepcopy(self.data)
        # Normalize empty optional strings to None
        for key in ["project_name", "tts_workflow", "ref_audio", "bgm_path", "editing_instruction"]:
            if isinstance(payload.get(key), str) and payload[key].strip() == "":
                payload[key] = None
        # Multiple assets with paragraph mode → switch to sentence so each
        # asset gets at least one scene instead of all repeating the first.
        asset_paths = payload.get("asset_paths", [])
        if len(asset_paths) > 1 and payload.get("split_mode") == "paragraph":
            payload["split_mode"] = "sentence"
        return payload


def create_intake_state(draft: dict[str, Any] | None = None) -> IntakeState:
    return IntakeState(draft=draft)
