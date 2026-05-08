from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from session_bridge import VideoEditSessionBridge
from upload_to_oss import upload_file_to_oss
from skills.video_edit_assistant_adapter import run_video_edit_intake

TRIGGER_PREFIXES = ('/video-edit', 'video-edit:', '视频剪辑：')


def _post_json(url: str, payload: dict):
    import urllib.request
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _extract_aspect_ratio(text: str) -> str | None:
    text = text or ''
    if '竖屏' in text or '9:16' in text:
        return '9:16'
    if '横屏' in text or '16:9' in text:
        return '16:9'
    if '方形' in text or '1:1' in text:
        return '1:1'
    return None


def _extract_duration_target(text: str) -> int | None:
    m = re.search(r'(\d+)\s*秒', text or '')
    if m:
        return int(m.group(1))
    return None


def _strip_trigger(text: str) -> str:
    s = (text or '').strip()
    for prefix in TRIGGER_PREFIXES:
        if s.startswith(prefix):
            return s[len(prefix):].strip()
    return s


def build_patch_from_message(text: str, media_paths: list[str] | None = None) -> dict[str, Any]:
    raw = (text or '').strip()
    content = _strip_trigger(raw)
    patch: dict[str, Any] = {}

    if content:
        # Very lightweight heuristics for MVP bridge
        if any(k in content for k in ['帮我做', '做一个', '产品视频', '介绍视频']):
            patch['project_name'] = content[:80]
        if content.startswith('文案：') or '文案：' in content:
            patch['script_text'] = content.split('文案：', 1)[1].strip()
        if '配音：默认' in content or '默认音色' in content:
            patch['voice_id'] = 'zh-CN-YunjianNeural'
        if '默认 BGM' in content or 'BGM：默认' in content:
            patch['bgm_path'] = '/home/xvibe/.openclaw/workspace/Pixelle-Video/bgm/default.mp3'
        if '剪辑要求：' in content:
            patch['editing_instruction'] = content.split('剪辑要求：', 1)[1].strip()

        duration = _extract_duration_target(content)
        if duration:
            patch['duration_target'] = duration

    if media_paths:
        patch['asset_paths'] = media_paths

    return patch


def handle_video_edit_message(
    *,
    user_key: str,
    text: str,
    media_paths: list[str] | None = None,
    api_base: str = 'http://127.0.0.1:8011',
    upload_oss: bool = True,
) -> dict[str, Any]:
    aspect_ratio = _extract_aspect_ratio(text)
    patch = build_patch_from_message(text, media_paths=media_paths)

    bridge = VideoEditSessionBridge()

    def execute_func(payload: dict):
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
                    Path('/home/xvibe/.openclaw/workspace/Pixelle-Video-openclaw-snapshot') / 'output' / relative,
                    Path('/home/xvibe/.openclaw/workspace/Pixelle-Video') / 'output' / relative,
                ]
                for local_file in candidate_paths:
                    if local_file.exists():
                        result['oss'] = upload_file_to_oss(local_file)
                        break
        return result

    result = bridge.process_turn(
        user_key=user_key,
        patch=patch,
        aspect_ratio=aspect_ratio,
        adapter_func=lambda draft, patch, aspect_ratio: run_video_edit_intake(
            draft=draft,
            patch=patch,
            aspect_ratio=aspect_ratio,
        ),
        execute_func=execute_func,
    )

    if result.state == 'collecting':
        bullet_lines = ['已进入视频剪辑收集模式。', result.summary]
        if result.questions:
            for idx, q in enumerate(result.questions, 1):
                bullet_lines.append(f'{idx}. {q["prompt"]}')
        reply_text = '\n'.join(bullet_lines)
    else:
        oss_url = None
        if result.execution and result.execution.get('oss'):
            oss_url = result.execution['oss'].get('url')
        local_url = None
        if result.execution and result.execution.get('response'):
            local_url = result.execution['response'].get('video_url')
        reply_text = '视频已生成。'
        if oss_url:
            reply_text += f'\nOSS 链接：{oss_url}'
        elif local_url:
            reply_text += f'\n本地链接：{local_url}'

    return {
        'state': result.state,
        'patch': patch,
        'aspect_ratio': aspect_ratio,
        'reply_text': reply_text,
        'session_path': result.session_path,
        'draft': result.draft,
        'execution': result.execution,
    }
