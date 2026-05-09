from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _default_session_dir() -> Path:
    try:
        from skill_config import load_video_edit_config
        return Path(load_video_edit_config()['session_dir'])
    except Exception:
        return Path.home() / '.openclaw/workspace/memory/video-edit-sessions'


@dataclass
class SessionResult:
    state: str  # collecting | executed
    session_path: str
    draft: dict[str, Any]
    summary: str
    questions: list[dict[str, str]]
    payload: dict[str, Any] | None = None
    execution: dict[str, Any] | None = None


class VideoEditSessionBridge:
    def __init__(self, session_dir: str | Path | None = None):
        self.session_dir = Path(session_dir) if session_dir else _default_session_dir()
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, user_key: str) -> Path:
        safe = ''.join(ch if ch.isalnum() or ch in '-_.' else '_' for ch in user_key)
        return self.session_dir / f'{safe}.json'

    def load_draft(self, user_key: str) -> dict[str, Any] | None:
        path = self._session_path(user_key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding='utf-8'))

    def save_draft(self, user_key: str, draft: dict[str, Any]) -> str:
        path = self._session_path(user_key)
        path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding='utf-8')
        return str(path)

    def clear_draft(self, user_key: str) -> str:
        path = self._session_path(user_key)
        if path.exists():
            path.unlink()
        return str(path)

    def process_turn(
        self,
        *,
        user_key: str,
        patch: dict[str, Any],
        aspect_ratio: str | None,
        adapter_func,
        execute_func,
    ) -> SessionResult:
        draft = self.load_draft(user_key)
        result = adapter_func(draft=draft, patch=patch, aspect_ratio=aspect_ratio)
        session_path = self._session_path(user_key)

        if result.get('ready') and result.get('payload'):
            execution = execute_func(result['payload'])
            self.clear_draft(user_key)
            return SessionResult(
                state='executed',
                session_path=str(session_path),
                draft=result['draft'],
                summary=result['summary'],
                questions=[],
                payload=result['payload'],
                execution=execution,
            )

        saved = self.save_draft(user_key, result['draft'])
        return SessionResult(
            state='collecting',
            session_path=saved,
            draft=result['draft'],
            summary=result['summary'],
            questions=result.get('questions', []),
            payload=None,
            execution=None,
        )
