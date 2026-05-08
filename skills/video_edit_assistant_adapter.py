from __future__ import annotations

from dataclasses import asdict
from typing import Any

from skills.video_edit_assistant_runtime import RuntimeResponse, VideoEditAssistantRuntime, create_runtime


def run_video_edit_intake(
    patch: dict[str, Any] | None = None,
    *,
    draft: dict[str, Any] | None = None,
    aspect_ratio: str | None = None,
    question_limit: int = 3,
) -> dict[str, Any]:
    """
    Stateless adapter entrypoint.

    Useful when an outer agent/session stores the draft externally and wants a
    simple request/response function.
    """
    runtime = create_runtime(initial_draft=draft)
    response = runtime.ingest(
        patch=patch,
        aspect_ratio=aspect_ratio,
        question_limit=question_limit,
    )
    return runtime_response_to_dict(response)


def runtime_response_to_dict(response: RuntimeResponse) -> dict[str, Any]:
    return asdict(response)
