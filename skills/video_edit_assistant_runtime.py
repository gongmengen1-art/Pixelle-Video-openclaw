from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from skills.video_edit_intake import (
    IntakeState,
    MODE_LABELS,
    API_BACKED_MODES,
    create_intake_state,
)


@dataclass
class RuntimeResponse:
    ready: bool
    draft: dict[str, Any]
    missing_required: list[str]
    missing_recommended: list[str]
    questions: list[dict[str, str]]
    payload: dict[str, Any] | None
    summary: str


class VideoEditAssistantRuntime:
    """Conversation-oriented runtime for the video edit assistant intake flow."""

    def __init__(self, initial_draft: dict[str, Any] | None = None):
        self.state = create_intake_state(initial_draft)

    def ingest(
        self,
        patch: dict[str, Any] | None = None,
        *,
        aspect_ratio: str | None = None,
        question_limit: int = 3,
    ) -> RuntimeResponse:
        if patch:
            self.state.merge(patch)
        if aspect_ratio:
            self.state.apply_aspect_ratio(aspect_ratio)

        ready             = self.state.ready()
        missing_required  = self.state.missing_required_fields()
        missing_recommended = self.state.missing_recommended_fields()
        questions         = [] if ready else self.state.next_questions(limit=question_limit)
        payload           = self.state.build_api_payload() if ready else None
        summary           = self._build_summary(ready, missing_required, questions)

        return RuntimeResponse(
            ready=ready,
            draft=self.state.data,
            missing_required=missing_required,
            missing_recommended=missing_recommended,
            questions=questions,
            payload=payload,
            summary=summary,
        )

    def _build_summary(
        self,
        ready: bool,
        missing_required: list[str],
        questions: list[dict[str, str]],
    ) -> str:
        mode = self.state.current_mode()
        mode_label = MODE_LABELS.get(mode, '') if mode else ''

        if not mode:
            return '请先选择创作模式。'

        if mode not in API_BACKED_MODES:
            return f'📋 {mode_label}\n此模式需要 ComfyUI 支持，功能即将上线。'

        if ready:
            return f'✅ {mode_label} — 信息已齐，开始生成视频…'

        # Custom assets: waiting for user confirmation after assets received
        if missing_required == ['_confirmed']:
            n = len(self.state.data.get('asset_paths') or [])
            asset_word = '个素材' if n > 0 else '个素材'
            return (
                f'📋 {mode_label}\n'
                f'已收到 {n} {asset_word}。\n'
                f'如还有素材要补充，继续发送即可；全部准备好后发送「开始」来生成视频。'
            )

        if missing_required:
            joined = '、'.join(missing_required)
            return f'📋 {mode_label}\n还缺这些关键项：{joined}。'

        return f'📋 {mode_label} — 基础信息已齐，以下推荐项可按需补充。'


def create_runtime(initial_draft: dict[str, Any] | None = None) -> VideoEditAssistantRuntime:
    return VideoEditAssistantRuntime(initial_draft=initial_draft)
