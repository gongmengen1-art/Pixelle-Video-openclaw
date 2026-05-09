from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from session_bridge import VideoEditSessionBridge
from upload_to_oss import upload_file_to_oss
from workspace_cleaner import cleanup_task_dir
from skills.video_edit_assistant_adapter import run_video_edit_intake
from skills.video_edit_intake import (
    MODE_QUICK_CREATE, MODE_CUSTOM_ASSETS,
    MODE_DIGITAL_HUMAN, MODE_IMAGE_TO_VIDEO, MODE_ACTION_TRANSFER,
    MODE_LABELS,
)

TRIGGER_PREFIXES = ('/video-edit', 'video-edit:', '视频剪辑：')

# API endpoints per mode
_API_ROUTES = {
    MODE_QUICK_CREATE:  '/api/video/generate/sync',
    MODE_CUSTOM_ASSETS: '/api/video/scripted-asset-edit/sync',
}

# ── Mode detection ──────────────────────────────────────────────────────────

# Keywords that signal a specific mode (checked in priority order)
_MODE_KEYWORDS: list[tuple[str, list[str]]] = [
    (MODE_DIGITAL_HUMAN,   ['数字人口播', '数字人', '口播', 'digital human']),
    (MODE_IMAGE_TO_VIDEO,  ['图生视频', '图片生成视频', 'i2v', 'image to video']),
    (MODE_ACTION_TRANSFER, ['动作迁移', '动作转移', 'action transfer']),
    (MODE_QUICK_CREATE,    ['快速制作', '快速生成', '帮我写', 'AI写', '全自动', '主题生成']),
    (MODE_CUSTOM_ASSETS,   ['自定义素材', '我的素材', '自带素材', '素材剪辑']),
]

# Number / name → mode (for mode selection turn)
_MODE_SELECT_MAP: dict[str, str] = {
    '1': MODE_QUICK_CREATE,    '①': MODE_QUICK_CREATE,    '一': MODE_QUICK_CREATE,
    '2': MODE_CUSTOM_ASSETS,   '②': MODE_CUSTOM_ASSETS,   '二': MODE_CUSTOM_ASSETS,
    '3': MODE_DIGITAL_HUMAN,   '③': MODE_DIGITAL_HUMAN,   '三': MODE_DIGITAL_HUMAN,
    '4': MODE_IMAGE_TO_VIDEO,  '④': MODE_IMAGE_TO_VIDEO,  '四': MODE_IMAGE_TO_VIDEO,
    '5': MODE_ACTION_TRANSFER, '⑤': MODE_ACTION_TRANSFER, '五': MODE_ACTION_TRANSFER,
    # Name fragments
    '快速': MODE_QUICK_CREATE,    '快速制作': MODE_QUICK_CREATE,
    '自定义': MODE_CUSTOM_ASSETS,  '自定义素材': MODE_CUSTOM_ASSETS,
    '数字人': MODE_DIGITAL_HUMAN,  '口播': MODE_DIGITAL_HUMAN,
    '图生视频': MODE_IMAGE_TO_VIDEO,
    '动作迁移': MODE_ACTION_TRANSFER,
}


def _detect_mode(content: str, media_paths: list[str] | None) -> str | None:
    """Return a mode string if the content clearly signals one, else None."""
    for mode, keywords in _MODE_KEYWORDS:
        if any(k in content for k in keywords):
            return mode
    # Heuristic: user provided a script → custom_assets
    if '文案：' in content or '文案:' in content:
        return MODE_CUSTOM_ASSETS
    return None


def _detect_mode_selection(text: str) -> str | None:
    """Parse user's mode selection reply (number or name)."""
    t = text.strip()
    if t in _MODE_SELECT_MAP:
        return _MODE_SELECT_MAP[t]
    for fragment, mode in _MODE_SELECT_MAP.items():
        if len(fragment) > 1 and fragment in t:
            return mode
    return None


# ── Shared field extractors ─────────────────────────────────────────────────

_SECTION_MARKERS: list[tuple[str, list[str]]] = [
    ('script_text',         ['文案：', '文案:', '内容：', '内容:', '固定文案：']),
    ('text',                ['主题：', '主题:', '话题：']),
    ('voice_raw',           ['音色：', '音色:', '配音：', '配音:', '声音：']),
    ('bgm_raw',             ['BGM：', 'BGM:', 'bgm：', '背景音乐：']),
    ('editing_instruction', ['剪辑要求：', '剪辑要求:', '要求：', '剪辑说明：']),
    ('prompt',              ['描述：', '描述:', 'prompt：', 'Prompt：']),
    ('project_name',        ['项目名：', '标题：', '视频名：']),
]

_VOICE_MAP: dict[str, str] = {
    '晓晓': 'zh-CN-XiaoxiaoNeural', '小晓': 'zh-CN-XiaoxiaoNeural',
    '晓依': 'zh-CN-XiaoyiNeural',   '小依': 'zh-CN-XiaoyiNeural',
    '女声': 'zh-CN-XiaoxiaoNeural', '女':   'zh-CN-XiaoxiaoNeural',
    '云健': 'zh-CN-YunjianNeural',  '男声': 'zh-CN-YunjianNeural',
    '男':   'zh-CN-YunjianNeural',  '云希': 'zh-CN-YunxiNeural',
    '云扬': 'zh-CN-YunyangNeural',  '云野': 'zh-CN-YunyeNeural',
    '云枫': 'zh-CN-YunfengNeural',
}

_INSTRUCTION_TOKENS = (
    '快节奏', '慢节奏', '节奏快', '节奏慢', '节奏感强', '紧凑', '舒缓', '轻松',
    '淡入淡出', '溶解', '渐变', '滑动', '推拉', '无转场', '硬切', '直切',
    '无字幕', '不加字幕', '不要字幕', '去掉字幕', '加字幕', '带字幕',
)


def _parse_sections(content: str) -> dict[str, str]:
    hits: list[tuple[int, str, str]] = []
    for key, markers in _SECTION_MARKERS:
        for m in markers:
            pos = content.find(m)
            if pos >= 0:
                hits.append((pos, key, m))
                break
    hits.sort(key=lambda x: x[0])
    out: dict[str, str] = {}
    for i, (pos, key, marker) in enumerate(hits):
        end = hits[i + 1][0] if i + 1 < len(hits) else len(content)
        out[key] = content[pos + len(marker):end].strip()
    return out


def _map_voice(raw: str) -> str | None:
    r = raw.strip()
    if not r or r in ('默认', 'default', '系统默认', '默认音色'):
        return None
    for alias, vid in _VOICE_MAP.items():
        if alias in r:
            return vid
    if '-' in r and r.replace('-', '').replace('_', '').isalnum():
        return r
    return None


def _map_bgm(raw: str, cfg: dict) -> str | None:
    r = raw.strip().lower()
    if not r:
        return None
    if any(k in r for k in ('无', 'none', '不要', '关闭', '不加', '不用')):
        return ''
    if any(k in r for k in ('默认', 'default')):
        return cfg.get('default_bgm') or ''
    return None


def _extract_duration(text: str) -> int | None:
    # Negative lookbehind: avoid matching "前N秒"/"后N秒" which mean "first/last N seconds"
    m = re.search(r'(?<!前)(?<!后)(?<!内)(\d+)\s*秒', text or '')
    return int(m.group(1)) if m else None


def _extract_aspect_ratio(text: str) -> str | None:
    text = text or ''
    if '竖屏' in text or '9:16' in text:
        return '9:16'
    if '横屏' in text or '16:9' in text:
        return '16:9'
    if '方形' in text or '1:1' in text:
        return '1:1'
    return None


def _extract_n_scenes(text: str) -> int | None:
    m = re.search(r'(\d+)\s*[个場场]?场景', text or '')
    return int(m.group(1)) if m else None


def _extract_pace(text: str) -> str | None:
    if any(k in text for k in ('快节奏', '节奏快', '节奏感强', '紧凑')):
        return 'fast'
    if any(k in text for k in ('慢节奏', '节奏慢', '舒缓', '轻松')):
        return 'slow'
    return None


def _extract_transition(text: str) -> str | None:
    if any(k in text for k in ('淡入淡出', 'fade', '溶解', '渐变')):
        return 'fade'
    if any(k in text for k in ('滑动', 'slide', '推拉')):
        return 'slide'
    if any(k in text for k in ('无转场', '硬切', '直切')):
        return 'cut'
    return None


def _extract_subtitle(text: str) -> bool | None:
    if any(k in text for k in ('无字幕', '不加字幕', '不要字幕', '去掉字幕')):
        return False
    if any(k in text for k in ('加字幕', '带字幕', '显示字幕')):
        return True
    return None


def _clean_script(text: str) -> str:
    """Remove instruction tokens (pace/transition/subtitle/duration/scenes) from narration text."""
    for token in _INSTRUCTION_TOKENS:
        text = text.replace(token, '')
    # Remove standalone duration/scene-count patterns that are instructions, not narration
    text = re.sub(r'(?<!前)(?<!后)(?<!内)\d+\s*秒', '', text)
    text = re.sub(r'\d+\s*[个場场]场景', '', text)
    return re.sub(r'[ \t]{2,}', ' ', text).strip()


def _strip_trigger(text: str) -> str:
    s = (text or '').strip()
    for prefix in TRIGGER_PREFIXES:
        if s.startswith(prefix):
            return s[len(prefix):].strip()
    return s


def _get_cfg() -> dict:
    try:
        from skill_config import load_video_edit_config
        return load_video_edit_config()
    except Exception:
        return {}


# ── Per-mode patch builders ─────────────────────────────────────────────────

def _patch_quick_create(content: str, sections: dict, media_paths: list[str] | None, cfg: dict) -> dict:
    patch: dict[str, Any] = {'mode': MODE_QUICK_CREATE}

    if 'text' in sections and sections['text']:
        patch['text'] = _clean_script(sections['text'])
    elif 'script_text' in sections and sections['script_text']:
        # User said "固定文案：..." → fixed mode
        patch['text'] = _clean_script(sections['script_text'])
        patch['create_mode'] = 'fixed'
    elif content and not any(m in content for _, ms in _SECTION_MARKERS for m in ms):
        # Plain topic text (no markers) → clean and use as topic
        patch['text'] = _clean_script(content)[:200]

    if 'project_name' in sections:
        patch['project_name'] = sections['project_name'][:80]

    if 'voice_raw' in sections:
        vid = _map_voice(sections['voice_raw'])
        if vid:
            patch['voice_id'] = vid

    if 'bgm_raw' in sections:
        bgm = _map_bgm(sections['bgm_raw'], cfg)
        if bgm is not None:
            patch['bgm_path'] = bgm or None

    duration = _extract_duration(content)
    if duration:
        patch['duration_target'] = duration

    n_scenes = _extract_n_scenes(content)
    if n_scenes:
        patch['n_scenes'] = n_scenes

    subtitle = _extract_subtitle(content)
    if subtitle is not None:
        patch['subtitle_enabled'] = subtitle

    return patch


def _patch_custom_assets(content: str, sections: dict, media_paths: list[str] | None, cfg: dict) -> dict:
    patch: dict[str, Any] = {'mode': MODE_CUSTOM_ASSETS}

    if 'script_text' in sections and sections['script_text']:
        patch['script_text'] = _clean_script(sections['script_text'])

    if 'project_name' in sections and sections['project_name']:
        patch['project_name'] = sections['project_name'][:80]

    if 'editing_instruction' in sections and sections['editing_instruction']:
        patch['editing_instruction'] = sections['editing_instruction']

    if 'voice_raw' in sections:
        vid = _map_voice(sections['voice_raw'])
        if vid:
            patch['voice_id'] = vid

    if 'bgm_raw' in sections:
        bgm = _map_bgm(sections['bgm_raw'], cfg)
        if bgm is not None:
            patch['bgm_path'] = bgm or None

    duration = _extract_duration(content)
    if duration:
        patch['duration_target'] = duration

    pace = _extract_pace(content)
    if pace:
        patch['pace'] = pace

    transition = _extract_transition(content)
    if transition:
        patch['transition_style'] = transition

    subtitle = _extract_subtitle(content)
    if subtitle is not None:
        patch['subtitle_enabled'] = subtitle

    if media_paths:
        patch['asset_paths'] = media_paths
        if len(media_paths) > 1:
            patch['split_mode'] = 'sentence'

    return patch


def _patch_digital_human(content: str, sections: dict, media_paths: list[str] | None, cfg: dict) -> dict:
    patch: dict[str, Any] = {'mode': MODE_DIGITAL_HUMAN}

    if 'script_text' in sections:
        patch['text'] = sections['script_text']
    elif content:
        patch['text'] = content[:500]

    if media_paths:
        patch['asset_paths'] = media_paths

    # Audio source detection
    if any(k in content for k in ('TTS', 'tts', 'AI合成', 'AI 合成', '自动合成')):
        patch['audio_source'] = 'tts'
    elif media_paths and any(p.endswith(('.mp3', '.wav', '.m4a', '.aac')) for p in media_paths):
        patch['audio_source'] = 'upload'

    return patch


def _patch_image_to_video(content: str, sections: dict, media_paths: list[str] | None, cfg: dict) -> dict:
    patch: dict[str, Any] = {'mode': MODE_IMAGE_TO_VIDEO}

    prompt = sections.get('prompt') or content
    if prompt:
        patch['prompt'] = prompt[:300]

    if media_paths:
        patch['asset_paths'] = media_paths

    return patch


def _patch_action_transfer(content: str, sections: dict, media_paths: list[str] | None, cfg: dict) -> dict:
    patch: dict[str, Any] = {'mode': MODE_ACTION_TRANSFER}

    prompt = sections.get('prompt') or ''
    if prompt:
        patch['prompt'] = prompt[:300]

    if media_paths:
        videos = [p for p in media_paths if p.endswith(('.mp4', '.mov', '.avi', '.mkv'))]
        images = [p for p in media_paths if p.endswith(('.jpg', '.jpeg', '.png', '.webp'))]
        if videos:
            patch['reference_video'] = videos[0]
        if images:
            patch['target_image'] = images[0]
        # Remaining media without clear type
        if not videos and not images and len(media_paths) >= 2:
            patch['reference_video'] = media_paths[0]
            patch['target_image'] = media_paths[1]

    return patch


_PATCH_BUILDERS = {
    MODE_QUICK_CREATE:    _patch_quick_create,
    MODE_CUSTOM_ASSETS:   _patch_custom_assets,
    MODE_DIGITAL_HUMAN:   _patch_digital_human,
    MODE_IMAGE_TO_VIDEO:  _patch_image_to_video,
    MODE_ACTION_TRANSFER: _patch_action_transfer,
}


# ── Public: build_patch_from_message ───────────────────────────────────────

def build_patch_from_message(
    text: str,
    media_paths: list[str] | None = None,
    *,
    current_draft: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Parse a raw Telegram message into a partial draft patch.

    Steps:
    1. Auto-detect mode from content (or from mode-selection reply)
    2. If session has existing mode, keep it unless user switches
    3. Dispatch to mode-specific patch builder
    """
    cfg = _get_cfg()
    content = _strip_trigger((text or '').strip())
    sections = _parse_sections(content)
    aspect_ratio = _extract_aspect_ratio(content)

    session_mode = (current_draft or {}).get('mode')

    # Check if this is a mode-selection reply (when mode was not yet chosen)
    is_mode_selection = False
    if not session_mode:
        selected = _detect_mode_selection(content)
        if selected:
            # Pure mode-selection turn: only record mode, ask for content next
            return {'mode': selected}
        detected = _detect_mode(content, media_paths)
        session_mode = detected

    # Build mode-specific patch
    if session_mode and session_mode in _PATCH_BUILDERS:
        patch = _PATCH_BUILDERS[session_mode](content, sections, media_paths, cfg)
    else:
        # Mode still unknown — only record mode if detected; let intake ask
        patch = {}
        detected = _detect_mode(content, media_paths)
        if detected:
            patch['mode'] = detected

    # Aspect ratio applies to all modes that use frame_template
    if aspect_ratio:
        patch['_aspect_ratio'] = aspect_ratio   # carried to handle_video_edit_message

    return patch


# ── Video URL → local file ─────────────────────────────────────────────────

def _resolve_video_local_path(video_url: str, output_base: str) -> Path | None:
    if '/api/files/' not in video_url:
        return None
    relative = video_url.split('/api/files/', 1)[1]
    candidate = Path(output_base) / 'output' / relative
    return candidate if candidate.exists() else None


# ── API routing per mode ───────────────────────────────────────────────────

def _execute_api(payload: dict, api_base: str, cfg: dict, upload_oss: bool) -> dict:
    import urllib.request
    # _skill_mode carries the intake mode (quick_create / custom_assets / …)
    # payload['mode'] may be overloaded with API-level fields (generate/fixed)
    skill_mode = payload.get('_skill_mode') or payload.get('mode')

    mode = skill_mode   # alias for readability below

    # Non-API-backed modes
    if mode not in _API_ROUTES:
        label = MODE_LABELS.get(mode, mode)
        return {
            'status': 'unsupported',
            'message': f'{label} 需要 ComfyUI 支持，功能即将上线。',
        }

    route = _API_ROUTES[mode]
    # Strip internal routing hints before POST
    clean = {k: v for k, v in payload.items() if not k.startswith('_')}

    api_url = api_base.rstrip('/') + route
    req = urllib.request.Request(
        api_url,
        data=json.dumps(clean).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            response = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        try:
            detail = json.loads(body).get('detail', body)
        except Exception:
            detail = body
        return {
            'status': 'api_error',
            'http_status': exc.code,
            'message': detail,
        }

    result: dict[str, Any] = {'api_url': api_url, 'response': response}

    if upload_oss:
        output_base = cfg.get('output_base', '')
        video_url = response.get('video_url', '')
        local_file = _resolve_video_local_path(video_url, output_base)
        if local_file:
            task_id = local_file.parent.name
            oss_prefix = cfg.get('oss', {}).get('prefix', 'openclaw/video-edit/')
            object_key = f'{oss_prefix}{task_id}.mp4'
            result['oss'] = upload_file_to_oss(local_file, object_key=object_key)
            if result['oss'].get('status') == 200:
                cleanup_task_dir(local_file.parent)
        else:
            result['oss_skip_reason'] = f'local file not found for: {video_url}'

    return result


# ── Main entry point ───────────────────────────────────────────────────────

def handle_video_edit_message(
    *,
    user_key: str,
    text: str,
    media_paths: list[str] | None = None,
    api_base: str | None = None,
    upload_oss: bool = True,
) -> dict[str, Any]:
    cfg = _get_cfg()
    resolved_api_base = api_base or cfg.get('api_base', 'http://127.0.0.1:8011')

    bridge = VideoEditSessionBridge()
    current_draft = bridge.load_draft(user_key)

    patch = build_patch_from_message(text, media_paths=media_paths, current_draft=current_draft)
    aspect_ratio = patch.pop('_aspect_ratio', None) or _extract_aspect_ratio(text)

    def execute_func(payload: dict) -> dict:
        return _execute_api(payload, resolved_api_base, cfg, upload_oss)

    result = bridge.process_turn(
        user_key=user_key,
        patch=patch,
        aspect_ratio=aspect_ratio,
        adapter_func=lambda draft, patch, aspect_ratio: run_video_edit_intake(
            draft=draft, patch=patch, aspect_ratio=aspect_ratio,
        ),
        execute_func=execute_func,
    )

    if result.state == 'collecting':
        mode = (result.draft or {}).get('mode')
        if not mode:
            lines = [result.summary] + [q['prompt'] for q in result.questions]
        else:
            lines = [result.summary] + [
                f'{i+1}. {q["prompt"]}' for i, q in enumerate(result.questions)
            ]
        reply_text = '\n'.join(filter(None, lines))
    else:
        ex = result.execution or {}
        if ex.get('status') == 'unsupported':
            reply_text = ex.get('message', '此模式暂不支持。')
        elif ex.get('status') == 'api_error':
            reply_text = f"视频生成失败（HTTP {ex.get('http_status')}）：{ex.get('message', '未知错误')}"
        else:
            oss_url = (ex.get('oss') or {}).get('url')
            local_url = (ex.get('response') or {}).get('video_url')
            reply_text = '视频已生成。'
            if oss_url:
                reply_text += f'\nOSS 链接：{oss_url}'
            elif local_url:
                reply_text += f'\n本地链接：{local_url}'

    return {
        'state':        result.state,
        'patch':        patch,
        'aspect_ratio': aspect_ratio,
        'reply_text':   reply_text,
        'session_path': result.session_path,
        'draft':        result.draft,
        'execution':    result.execution,
    }
