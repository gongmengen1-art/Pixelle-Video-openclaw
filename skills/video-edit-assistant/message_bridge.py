from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from session_bridge import VideoEditSessionBridge
from upload_to_oss import upload_file_to_oss
from workspace_cleaner import cleanup_task_dir
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


def _get_cfg() -> dict:
    try:
        from skill_config import load_video_edit_config
        return load_video_edit_config()
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Structured field-section parser
# ---------------------------------------------------------------------------

# Each entry: (internal_key, list_of_trigger_strings)
# Order matters: earlier entries take precedence when positions overlap.
_SECTION_MARKERS: list[tuple[str, list[str]]] = [
    ('script_text',         ['文案：', '文案:', '内容：', '内容:']),
    ('voice_raw',           ['音色：', '音色:', '配音：', '配音:', '声音：', '声音:']),
    ('bgm_raw',             ['BGM：', 'BGM:', 'bgm：', 'bgm:', '背景音乐：', '背景音：']),
    ('editing_instruction', ['剪辑要求：', '剪辑要求:', '要求：', '剪辑说明：']),
    ('project_name',        ['项目名：', '项目名:', '标题：', '标题:', '视频名：']),
]

# Edge-TTS voice aliases (subset of tts_voices.py)
_VOICE_MAP: dict[str, str] = {
    '晓晓': 'zh-CN-XiaoxiaoNeural', '小晓': 'zh-CN-XiaoxiaoNeural',
    '晓依': 'zh-CN-XiaoyiNeural',   '小依': 'zh-CN-XiaoyiNeural',
    '女声': 'zh-CN-XiaoxiaoNeural', '女':   'zh-CN-XiaoxiaoNeural',
    '云健': 'zh-CN-YunjianNeural',  '男声': 'zh-CN-YunjianNeural',
    '男':   'zh-CN-YunjianNeural',  '云希': 'zh-CN-YunxiNeural',
    '云扬': 'zh-CN-YunyangNeural',  '云野': 'zh-CN-YunyeNeural',
    '云枫': 'zh-CN-YunfengNeural',
}


def _parse_sections(content: str) -> dict[str, str]:
    """
    Split content into named sections using field markers as boundaries.

    Example input:
      "帮我做个视频 文案：产品功能强大 音色：女声 BGM：默认 剪辑要求：前3秒抓人"
    Returns:
      {'script_text': '产品功能强大', 'voice_raw': '女声',
       'bgm_raw': '默认', 'editing_instruction': '前3秒抓人'}
    """
    hits: list[tuple[int, str, str]] = []
    for key, markers in _SECTION_MARKERS:
        for m in markers:
            pos = content.find(m)
            if pos >= 0:
                hits.append((pos, key, m))
                break  # first matching marker wins for this key
    hits.sort(key=lambda x: x[0])

    sections: dict[str, str] = {}
    for i, (pos, key, marker) in enumerate(hits):
        end = hits[i + 1][0] if i + 1 < len(hits) else len(content)
        sections[key] = content[pos + len(marker):end].strip()
    return sections


def _map_voice(raw: str) -> str | None:
    """Return a concrete voice_id, or None to keep the system default."""
    raw = raw.strip()
    if not raw or raw in ('默认', 'default', '系统默认', '默认音色'):
        return None
    for alias, vid in _VOICE_MAP.items():
        if alias in raw:
            return vid
    # Already a full voice ID (e.g. "zh-CN-XiaoxiaoNeural")
    if '-' in raw and raw.replace('-', '').replace('_', '').isalnum():
        return raw
    return None


def _map_bgm(raw: str, cfg: dict) -> str | None:
    """Return bgm_path string, '' for explicit no-BGM, None if not stated."""
    r = raw.strip().lower()
    if not r:
        return None
    if any(k in r for k in ('无', 'none', '不要', '关闭', '不加', '不用')):
        return ''  # empty string → no BGM in payload
    if any(k in r for k in ('默认', 'default')):
        default = cfg.get('default_bgm', '')
        return default if default else ''
    return None


def _extract_pace(content: str) -> str | None:
    if any(k in content for k in ('快节奏', '节奏快', '节奏感强', '紧凑')):
        return 'fast'
    if any(k in content for k in ('慢节奏', '节奏慢', '舒缓', '轻松')):
        return 'slow'
    return None


def _extract_transition(content: str) -> str | None:
    if any(k in content for k in ('淡入淡出', 'fade', '溶解', '渐变')):
        return 'fade'
    if any(k in content for k in ('滑动', 'slide', '推拉')):
        return 'slide'
    if any(k in content for k in ('无转场', '硬切', '直切')):
        return 'cut'
    return None


def _extract_subtitle(content: str) -> bool | None:
    if any(k in content for k in ('无字幕', '不加字幕', '不要字幕', '去掉字幕')):
        return False
    if any(k in content for k in ('加字幕', '带字幕', '显示字幕', '开启字幕')):
        return True
    return None


# Keywords that are purely instructions and should not appear in narration.
_INSTRUCTION_TOKENS = (
    '快节奏', '慢节奏', '节奏快', '节奏慢', '节奏感强', '紧凑', '舒缓', '轻松',
    '淡入淡出', '溶解', '渐变', '滑动', '推拉', '无转场', '硬切', '直切',
    '无字幕', '不加字幕', '不要字幕', '去掉字幕', '加字幕', '带字幕', '显示字幕',
)

def _clean_script_text(text: str) -> str:
    """Remove trailing instruction tokens that leaked into the script section."""
    result = text
    for token in _INSTRUCTION_TOKENS:
        result = result.replace(token, '')
    # Collapse multiple spaces / punctuation left behind
    result = re.sub(r'[ \t]{2,}', ' ', result).strip()
    return result


# ---------------------------------------------------------------------------
# Public patch builder
# ---------------------------------------------------------------------------

def build_patch_from_message(text: str, media_paths: list[str] | None = None) -> dict[str, Any]:
    """
    Parse a raw Telegram message into a partial draft patch.

    Handles structured fields (文案：/音色：/BGM：/剪辑要求：) as explicit
    section markers — content for each field stops at the next marker.
    Also extracts inline signals (duration, pace, transition, subtitle)
    from anywhere in the text.
    """
    cfg = _get_cfg()
    raw = (text or '').strip()
    content = _strip_trigger(raw)
    patch: dict[str, Any] = {}

    # ── Structured section parsing ────────────────────────────────────────
    sections = _parse_sections(content)

    if 'script_text' in sections and sections['script_text']:
        patch['script_text'] = _clean_script_text(sections['script_text'])

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
            patch['bgm_path'] = bgm or None  # '' → None (no BGM)

    # ── Fallback heuristic title from unstructured intent ────────────────
    if not patch.get('project_name'):
        if any(k in content for k in ('帮我做', '做一个', '产品视频', '介绍视频')):
            # Grab text before first section marker as title hint
            first_hit = next(
                (content.find(m) for _, ms in _SECTION_MARKERS for m in ms if content.find(m) >= 0),
                80,
            )
            patch['project_name'] = content[:min(first_hit, 80)].strip() or None

    # ── Inline signal extraction ──────────────────────────────────────────
    duration = _extract_duration_target(content)
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

    # ── Media assets + auto split-mode ───────────────────────────────────
    if media_paths:
        patch['asset_paths'] = media_paths
        # Multiple assets: switch to sentence split so each asset gets a segment
        if len(media_paths) > 1:
            patch['split_mode'] = 'sentence'

    return patch


def _resolve_video_local_path(video_url: str, output_base: str) -> Path | None:
    """
    Convert an API video_url back to a local file path for OSS upload.

    The API returns URLs like: http://host:port/api/files/{task_id}/final.mp4
    The local file lives at:   {output_base}/output/{task_id}/final.mp4
    """
    if '/api/files/' not in video_url:
        return None
    relative = video_url.split('/api/files/', 1)[1]
    # path_to_url strips the "output/" prefix; add it back
    candidate = Path(output_base) / 'output' / relative
    return candidate if candidate.exists() else None


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
    output_base = cfg.get('output_base', '')

    aspect_ratio = _extract_aspect_ratio(text)
    patch = build_patch_from_message(text, media_paths=media_paths)

    bridge = VideoEditSessionBridge()

    def execute_func(payload: dict):
        api_url = resolved_api_base.rstrip('/') + '/api/video/scripted-asset-edit/sync'
        response = _post_json(api_url, payload)
        result: dict[str, Any] = {'api_url': api_url, 'response': response}
        if upload_oss:
            video_url = response.get('video_url', '')
            local_file = _resolve_video_local_path(video_url, output_base)
            if local_file:
                task_id = local_file.parent.name  # e.g. "20260508_221018_f2a2"
                oss_prefix = cfg.get('oss', {}).get('prefix', 'openclaw/video-edit/')
                object_key = f'{oss_prefix}{task_id}.mp4'
                result['oss'] = upload_file_to_oss(local_file, object_key=object_key)
                # OSS 上传成功后立即清理本地任务目录（中间文件 + 最终视频）
                if result['oss'].get('status') == 200:
                    cleanup_task_dir(local_file.parent)
            else:
                result['oss_skip_reason'] = f'local file not found for: {video_url}'
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
        lines = ['已进入视频剪辑收集模式。', result.summary]
        for idx, q in enumerate(result.questions, 1):
            lines.append(f'{idx}. {q["prompt"]}')
        reply_text = '\n'.join(lines)
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
