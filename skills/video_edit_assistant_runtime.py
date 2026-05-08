from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from skills.video_edit_intake import IntakeState, create_intake_state


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
        """
        Merge a user-provided patch, optionally map aspect ratio, and return
        the next runtime state.
        """
        if patch:
            self.state.merge(patch)
        if aspect_ratio:
            self.state.apply_aspect_ratio(aspect_ratio)

        ready = self.state.ready()
        missing_required = self.state.missing_required_fields()
        missing_recommended = self.state.missing_recommended_fields()
        questions = [] if ready else self.state.next_questions(limit=question_limit)
        payload = self.state.build_api_payload() if ready else None
        summary = self._build_summary(ready, missing_required, questions)

        return RuntimeResponse(
            ready=ready,
            draft=self.state.build_api_payload(),
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
        if ready:
            return "信息已齐，可以直接调用 /api/video/scripted-asset-edit/sync 生成 demo 视频。"

        if missing_required:
            joined = "、".join(missing_required)
            return f"还缺这些关键项：{joined}。"

        if questions:
            return "基础信息已齐，如果你愿意，我还可以继续补齐推荐项。"

        return "当前草稿已更新。"


def create_runtime(initial_draft: dict[str, Any] | None = None) -> VideoEditAssistantRuntime:
    return VideoEditAssistantRuntime(initial_draft=initial_draft)
