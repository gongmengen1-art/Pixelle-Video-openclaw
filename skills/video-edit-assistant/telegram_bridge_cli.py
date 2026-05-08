from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

_skill_dir = Path(__file__).resolve().parent
_project_root = _skill_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
if str(_skill_dir) not in sys.path:
    sys.path.insert(0, str(_skill_dir))

from skills.video_edit_assistant_adapter import run_video_edit_intake
from session_bridge import VideoEditSessionBridge
from upload_to_oss import upload_file_to_oss


def _load_json_arg(value: str | None):
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    p = Path(value)
    if p.exists() and p.is_file():
        return json.loads(p.read_text(encoding='utf-8'))
    return json.loads(value)


def _post_json(url: str, payload: dict):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _execute(payload: dict, api_base: str, upload_oss: bool):
    api_url = api_base.rstrip('/') + '/api/video/scripted-asset-edit/sync'
    response = _post_json(api_url, payload)
    result = {
        'api_url': api_url,
        'response': response,
    }
    if upload_oss:
        video_url = response.get('video_url')
        if video_url and '/api/files/' in video_url:
            relative = video_url.split('/api/files/', 1)[1]
            candidate_paths = [
                _project_root / 'output' / relative,
                Path('/home/xvibe/.openclaw/workspace/Pixelle-Video') / 'output' / relative,
            ]
            for local_file in candidate_paths:
                if local_file.exists():
                    result['oss'] = upload_file_to_oss(local_file)
                    break
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description='Telegram-style /video-edit bridge CLI')
    parser.add_argument('--user-key', required=True, help='Stable user/session key, e.g. telegram-7217243523')
    parser.add_argument('--patch', required=True, help='Patch JSON string or path')
    parser.add_argument('--aspect-ratio', default=None)
    parser.add_argument('--api-base', default='http://127.0.0.1:8011')
    parser.add_argument('--upload-oss', action='store_true')
    parser.add_argument('--pretty', action='store_true')
    args = parser.parse_args()

    bridge = VideoEditSessionBridge()
    patch = _load_json_arg(args.patch)
    result = bridge.process_turn(
        user_key=args.user_key,
        patch=patch,
        aspect_ratio=args.aspect_ratio,
        adapter_func=lambda draft, patch, aspect_ratio: run_video_edit_intake(
            draft=draft,
            patch=patch,
            aspect_ratio=aspect_ratio,
        ),
        execute_func=lambda payload: _execute(payload, args.api_base, args.upload_oss),
    )

    output = {
        'state': result.state,
        'session_path': result.session_path,
        'draft': result.draft,
        'summary': result.summary,
        'questions': result.questions,
        'payload': result.payload,
        'execution': result.execution,
    }
    if args.pretty:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
