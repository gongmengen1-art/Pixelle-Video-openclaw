from __future__ import annotations

from copy import deepcopy
from typing import Any

# ── Mode constants ───────────────────────────────────────────────────────────

MODE_QUICK_CREATE    = 'quick_create'
MODE_CUSTOM_ASSETS   = 'custom_assets'
MODE_DIGITAL_HUMAN   = 'digital_human'
MODE_IMAGE_TO_VIDEO  = 'image_to_video'
MODE_ACTION_TRANSFER = 'action_transfer'

MODE_LABELS: dict[str, str] = {
    MODE_QUICK_CREATE:    '⚡ 快速制作（给主题，AI 生成文案 + TTS 配音）',
    MODE_CUSTOM_ASSETS:   '🎨 自定义素材（你提供文案和图片/视频素材）',
    MODE_DIGITAL_HUMAN:   '🤖 数字人口播（上传形象图，AI 合成口播视频）',
    MODE_IMAGE_TO_VIDEO:  '🎥 图生视频（上传图片，AI 生成动态视频）',
    MODE_ACTION_TRANSFER: '💃 动作迁移（上传参考动作视频 + 目标图片）',
}

# ── Default draft per mode ───────────────────────────────────────────────────

_SHARED_DEFAULTS: dict[str, Any] = {
    'mode':            None,
    'project_name':    '',
    'frame_template':  '1080x1920/asset_default.html',
    'voice_id':        'zh-CN-YunjianNeural',
    'tts_workflow':    None,
    'ref_audio':       None,
    'tts_speed':       1.0,
    'subtitle_enabled': True,
    'bgm_path':        None,
    'bgm_volume':      0.2,
    'bgm_mode':        'loop',
    'source':          'selfhost',
}

MODE_DEFAULTS: dict[str | None, dict[str, Any]] = {
    MODE_QUICK_CREATE: {
        **_SHARED_DEFAULTS,
        'mode':           MODE_QUICK_CREATE,
        'frame_template': '1080x1920/static_default.html',   # static: no image generation needed
        'text':           '',
        'create_mode':    'generate',   # 'generate' | 'fixed'
        'n_scenes':       5,
        'duration_target': 30,
        'pace':           'medium',
        'split_mode':     'paragraph',  # only used when create_mode=fixed
    },
    MODE_CUSTOM_ASSETS: {
        **_SHARED_DEFAULTS,
        'mode':                 MODE_CUSTOM_ASSETS,
        'script_text':          '',
        'asset_paths':          [],
        'split_mode':           'paragraph',
        'duration_target':      30,
        'skip_asset_analysis':  True,
        'allow_asset_reuse':    True,
        'pace':                 'medium',
        'transition_style':     'simple',
        'editing_instruction':  None,
    },
    MODE_DIGITAL_HUMAN: {
        **_SHARED_DEFAULTS,
        'mode':         MODE_DIGITAL_HUMAN,
        'asset_paths':  [],     # character image(s)
        'text':         '',     # script for TTS
        'audio_source': None,   # 'tts' | 'upload'
        'dh_workflow':  None,
    },
    MODE_IMAGE_TO_VIDEO: {
        **_SHARED_DEFAULTS,
        'mode':         MODE_IMAGE_TO_VIDEO,
        'asset_paths':  [],
        'prompt':       '',
        'i2v_workflow': None,
    },
    MODE_ACTION_TRANSFER: {
        **_SHARED_DEFAULTS,
        'mode':             MODE_ACTION_TRANSFER,
        'reference_video':  None,
        'target_image':     None,
        'prompt':           '',
        'af_workflow':      None,
    },
}

# ── Required fields per mode ─────────────────────────────────────────────────

MODE_REQUIRED_FIELDS: dict[str | None, list[str]] = {
    None:                [],   # mode unknown — prompt for mode first
    MODE_QUICK_CREATE:   ['text', 'frame_template'],
    MODE_CUSTOM_ASSETS:  ['script_text', 'asset_paths', 'frame_template'],
    MODE_DIGITAL_HUMAN:  ['asset_paths', 'audio_source'],
    MODE_IMAGE_TO_VIDEO: ['asset_paths', 'prompt'],
    MODE_ACTION_TRANSFER: ['reference_video', 'target_image', 'prompt'],
}

# ── Recommended (optional but nice-to-have) per mode ────────────────────────

MODE_RECOMMENDED_FIELDS: dict[str | None, list[str]] = {
    None:                [],
    MODE_QUICK_CREATE:   ['tts_workflow', 'ref_audio', 'bgm_path'],
    MODE_CUSTOM_ASSETS:  ['tts_workflow', 'ref_audio', 'bgm_path', 'editing_instruction'],
    MODE_DIGITAL_HUMAN:  [],
    MODE_IMAGE_TO_VIDEO: [],
    MODE_ACTION_TRANSFER: [],
}

# ── Per-mode field prompts ───────────────────────────────────────────────────

_MODE_SELECT_PROMPT = (
    '请选择创作模式（回复序号或模式名）：\n'
    + '\n'.join(f'  {i+1}. {label}' for i, label in enumerate(MODE_LABELS.values()))
)

MODE_FIELD_PROMPTS: dict[str, dict[str, str]] = {
    MODE_QUICK_CREATE: {
        'text': (
            '请告诉我视频主题，AI 会自动生成文案和配音（如"如何提升工作效率"）。\n'
            '如果你已有文案，发给我并加上"固定文案："前缀。\n'
            '注：AI 配图功能暂未开放，视频将使用纯文字排版样式。'
        ),
        'frame_template': '你要竖屏（9:16）、横屏（16:9）还是方形（1:1）？',
        'n_scenes':       '视频分几个场景？默认 5 个，可以说"3 个场景"。',
        'tts_workflow':   '你要用默认音色，还是指定一个 TTS 工作流？',
        'ref_audio':      '如果你想声音克隆，请发一段 mp3/wav 参考音频；不需要就跳过。',
        'bgm_path':       '要加背景音乐吗？说"默认 BGM"或发一个音频文件，不要就跳过。',
    },
    MODE_CUSTOM_ASSETS: {
        'script_text':          '请把完整文案发给我，我会按段落或句子拆成视频场景。',
        'asset_paths':          '请把图片或视频素材发给我；多个文件会按顺序匹配文案场景。',
        'frame_template':       '你要竖屏（9:16）、横屏（16:9）还是方形（1:1）？',
        'tts_workflow':         '你要用默认音色，还是指定一个 TTS 工作流？',
        'ref_audio':            '如果你想声音克隆，请发一段 mp3/wav 参考音频；不需要就跳过。',
        'bgm_path':             '要加背景音乐吗？说"默认 BGM"或发一个音频文件，不要就跳过。',
        'editing_instruction':  '对节奏、转场或重点有特殊要求吗？（可选，不填跳过）',
    },
    MODE_DIGITAL_HUMAN: {
        'asset_paths':  '请发一张数字人形象图（正面、清晰）。',
        'audio_source': '口播音频来源：回复"TTS"用 AI 合成，或直接上传录音文件。',
        'text':         '请输入口播文案，AI 来合成语音。',
    },
    MODE_IMAGE_TO_VIDEO: {
        'asset_paths':   '请把要生成视频的图片发给我（支持多张）。',
        'prompt':        '请描述图片如何动起来，例如"镜头缓缓推进，背景微风吹拂"。',
        'i2v_workflow':  '使用哪个图生视频工作流？留空自动选择。',
    },
    MODE_ACTION_TRANSFER: {
        'reference_video': '请发一段包含参考动作的视频（最长 30 秒）。',
        'target_image':    '请发一张目标角色的图片，动作将迁移到这张图上。',
        'prompt':          '请描述画面风格或补充说明（可选）。',
    },
}

# Default aspect-ratio → template mapping (custom_assets / unknown mode)
FRAME_TEMPLATE_BY_RATIO: dict[str, str] = {
    '9:16': '1080x1920/asset_default.html',
    '16:9': '1920x1080/image_full.html',
    '1:1':  '1080x1080/image_minimal_framed.html',
}

# Per-mode aspect-ratio → template overrides.
# quick_create defaults to static templates (no image generation required).
# Switch to image_* templates once RunningHub / ComfyUI is configured.
_MODE_RATIO_TO_TEMPLATE: dict[str | None, dict[str, str]] = {
    MODE_QUICK_CREATE: {
        '9:16': '1080x1920/static_default.html',
        '16:9': '1080x1920/static_default.html',  # no 16:9 static template yet; fall back
        '1:1':  '1080x1920/static_default.html',  # no 1:1 static template yet; fall back
    },
}

# Modes backed by a REST API (others need direct ComfyUI)
API_BACKED_MODES = {MODE_QUICK_CREATE, MODE_CUSTOM_ASSETS}


# ── IntakeState ──────────────────────────────────────────────────────────────

class IntakeState:
    """
    Mutable draft state for the video edit assistant.
    Mode-aware: required fields and payload format vary by mode.
    """

    def __init__(self, draft: dict[str, Any] | None = None):
        self.data: dict[str, Any] = {'mode': None}
        if draft:
            self.merge(draft)

    # ── Internal helpers ──────────────────────────────────────────────────

    def _load_mode_defaults(self) -> None:
        """Fill in mode-specific defaults (without overwriting existing values)."""
        mode = self.data.get('mode')
        if mode and mode in MODE_DEFAULTS:
            for k, v in MODE_DEFAULTS[mode].items():
                if k not in self.data:
                    self.data[k] = deepcopy(v)

    def _allowed_keys(self) -> set[str]:
        mode = self.data.get('mode')
        keys = set(self.data.keys()) | {'mode'}
        if mode and mode in MODE_DEFAULTS:
            keys |= set(MODE_DEFAULTS[mode].keys())
        return keys

    # ── Public API ────────────────────────────────────────────────────────

    def merge(self, patch: dict[str, Any]) -> dict[str, Any]:
        """Merge a partial user patch into the draft."""
        # Handle mode first so defaults are available for subsequent keys
        if patch.get('mode'):
            self.data['mode'] = patch['mode']
            self._load_mode_defaults()

        allowed = self._allowed_keys()
        for key, value in patch.items():
            if key == 'mode':
                continue
            if key not in allowed:
                continue
            if value is None:
                continue
            if key == 'asset_paths':
                if isinstance(value, list):
                    cleaned = [str(v).strip() for v in value if str(v).strip()]
                    if cleaned:
                        self.data[key] = cleaned
                elif isinstance(value, str) and value.strip():
                    self.data[key] = [value.strip()]
                continue
            if isinstance(value, str):
                value = value.strip()
                if value == '':
                    continue
            self.data[key] = value
        return self.data

    def apply_aspect_ratio(self, ratio: str | None) -> str | None:
        if not ratio:
            return None
        mode = self.data.get('mode')
        mapping = _MODE_RATIO_TO_TEMPLATE.get(mode, FRAME_TEMPLATE_BY_RATIO)
        template = mapping.get(ratio.strip())
        if template:
            self.data['frame_template'] = template
        return template

    def current_mode(self) -> str | None:
        return self.data.get('mode')

    def missing_required_fields(self) -> list[str]:
        mode = self.data.get('mode')
        missing = []
        for field in MODE_REQUIRED_FIELDS.get(mode, []):
            value = self.data.get(field)
            if value is None:
                missing.append(field)
            elif isinstance(value, str) and not value.strip():
                missing.append(field)
            elif isinstance(value, list) and len(value) == 0:
                missing.append(field)
        return missing

    def missing_recommended_fields(self) -> list[str]:
        mode = self.data.get('mode')
        missing = []
        for field in MODE_RECOMMENDED_FIELDS.get(mode, []):
            value = self.data.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(field)
        return missing

    def next_questions(self, limit: int = 3) -> list[dict[str, str]]:
        mode = self.data.get('mode')

        # Mode not selected yet → ask first
        if not mode:
            return [{'field': 'mode', 'prompt': _MODE_SELECT_PROMPT}]

        fields = self.missing_required_fields()
        if len(fields) < limit:
            for field in self.missing_recommended_fields():
                if field not in fields:
                    fields.append(field)
                if len(fields) >= limit:
                    break

        prompts = MODE_FIELD_PROMPTS.get(mode, {})
        return [
            {'field': f, 'prompt': prompts.get(f, f'请补充：{f}')}
            for f in fields[:limit]
        ]

    def ready(self) -> bool:
        mode = self.data.get('mode')
        if not mode:
            return False
        if mode not in API_BACKED_MODES:
            return False   # ComfyUI modes not yet API-backed
        return len(self.missing_required_fields()) == 0

    def build_api_payload(self) -> dict[str, Any] | None:
        """Build the API request payload based on the current mode."""
        mode = self.data.get('mode')
        if not mode:
            return None

        d = self.data

        if mode == MODE_QUICK_CREATE:
            payload: dict[str, Any] = {
                '_skill_mode':      MODE_QUICK_CREATE,   # routing hint, stripped before POST
                'text':             d.get('text', ''),
                'mode':             d.get('create_mode', 'generate'),
                'title':            d.get('project_name') or None,
                'n_scenes':         d.get('n_scenes', 5),
                'frame_template':   d.get('frame_template'),
                'voice_id':         d.get('voice_id'),
                'tts_workflow':     d.get('tts_workflow'),
                'ref_audio':        d.get('ref_audio'),
                'tts_speed':        d.get('tts_speed', 1.0),
                'bgm_path':         d.get('bgm_path'),
                'bgm_volume':       d.get('bgm_volume', 0.2),
                'bgm_mode':         d.get('bgm_mode', 'loop'),
                'subtitle_enabled': d.get('subtitle_enabled', True),
                'split_mode':       d.get('split_mode', 'paragraph'),
            }

        elif mode == MODE_CUSTOM_ASSETS:
            payload = {
                'script_text':         d.get('script_text', ''),
                'asset_paths':         d.get('asset_paths', []),
                'project_name':        d.get('project_name') or None,
                'split_mode':          d.get('split_mode', 'paragraph'),
                'duration_target':     d.get('duration_target', 30),
                'skip_asset_analysis': d.get('skip_asset_analysis', True),
                'allow_asset_reuse':   d.get('allow_asset_reuse', True),
                'frame_template':      d.get('frame_template'),
                'voice_id':            d.get('voice_id'),
                'tts_workflow':        d.get('tts_workflow'),
                'ref_audio':           d.get('ref_audio'),
                'tts_speed':           d.get('tts_speed', 1.0),
                'subtitle_enabled':    d.get('subtitle_enabled', True),
                'bgm_path':            d.get('bgm_path'),
                'bgm_volume':          d.get('bgm_volume', 0.2),
                'bgm_mode':            d.get('bgm_mode', 'loop'),
                'pace':                d.get('pace', 'medium'),
                'transition_style':    d.get('transition_style', 'simple'),
                'editing_instruction': d.get('editing_instruction'),
                'source':              d.get('source', 'selfhost'),
            }
            # Multi-asset: sentence split ensures each asset gets a scene
            if len(payload['asset_paths']) > 1 and payload['split_mode'] == 'paragraph':
                payload['split_mode'] = 'sentence'

        else:
            return None   # ComfyUI modes not yet REST-backed

        # Normalize empty strings → None for optional fields
        optional = ['title', 'project_name', 'tts_workflow', 'ref_audio',
                    'bgm_path', 'editing_instruction']
        for k in optional:
            if k in payload and isinstance(payload.get(k), str) and not payload[k].strip():
                payload[k] = None

        return payload


def create_intake_state(draft: dict[str, Any] | None = None) -> IntakeState:
    return IntakeState(draft=draft)
