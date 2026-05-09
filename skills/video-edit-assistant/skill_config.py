from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_skill_dir = Path(__file__).resolve().parent
_project_root = _skill_dir.parent.parent


def _find_config_path() -> Path:
    env = os.environ.get('PIXELLE_VIDEO_CONFIG')
    if env:
        return Path(env)
    return _project_root / 'config.yaml'


def _expand(value: str) -> str:
    return os.path.expanduser(os.path.expandvars(str(value)))


def load_video_edit_config() -> dict[str, Any]:
    """Return the video_edit section from config.yaml with defaults applied."""
    raw: dict = {}
    try:
        import yaml
        path = _find_config_path()
        if path.exists():
            with open(path, encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            raw = data.get('video_edit', {}) or {}
    except Exception:
        pass

    default_bgm = str(_project_root / 'bgm' / 'default.mp3')
    return {
        'api_base': raw.get('api_base') or 'http://127.0.0.1:8011',
        'session_dir': _expand(raw.get('session_dir') or '~/.openclaw/workspace/memory/video-edit-sessions'),
        'output_base': _expand(raw.get('output_base') or str(_project_root)),
        'default_bgm': _expand(raw.get('default_bgm') or default_bgm),
        'oss': dict(raw.get('oss') or {}),
    }
