# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Subtitle utilities: text splitting + MoviePy PIL-based subtitle overlay.

Uses PIL to render subtitle text (avoids ImageMagick dependency) and MoviePy
for video compositing.
"""

import os
from typing import Optional
from loguru import logger


# ── Text splitting ──────────────────────────────────────────────────────────

def split_text_into_lines(text: str, max_chars: int) -> list[str]:
    """
    Split text into lines of at most max_chars characters each.
    Character-based splitting works correctly for Chinese/Japanese/Korean text.
    """
    lines: list[str] = []
    for para in text.split('\n'):
        para = para.strip()
        if not para:
            continue
        cur = ''
        for ch in para:
            cur += ch
            if len(cur) >= max_chars:
                lines.append(cur)
                cur = ''
        if cur:
            lines.append(cur)
    return lines or [text.strip()]


def split_narration_to_segments(
    text: str,
    max_chars: int,
    max_lines: int = 2,
) -> list[str]:
    """
    Group split lines into subtitle display segments.
    Each segment contains at most max_lines lines and is shown for an equal
    fraction of the total frame duration.
    """
    lines = split_text_into_lines(text, max_chars)
    segments: list[str] = []
    for i in range(0, len(lines), max_lines):
        segments.append('\n'.join(lines[i:i + max_lines]))
    return segments or [text.strip()]


# ── Font detection ──────────────────────────────────────────────────────────

def find_cjk_font() -> Optional[str]:
    """Find a CJK-capable TrueType/OpenType font file on the system."""
    candidates = [
        # macOS
        '/System/Library/Fonts/PingFang.ttc',
        '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
        '/Library/Fonts/Arial Unicode MS.ttf',
        # Linux Noto CJK
        '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/noto/NotoSansSC-Regular.otf',
        '/usr/share/fonts/opentype/noto/NotoSansSC-Regular.otf',
        # Linux WQY
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        '/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc',
        # Linux fallbacks
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    ]
    for path in candidates:
        if os.path.isfile(path):
            logger.debug(f"CJK font found: {path}")
            return path

    # Try fontconfig
    try:
        import subprocess
        result = subprocess.run(
            ['fc-match', '-f', '%{file}', 'sans:lang=zh'],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            path = result.stdout.strip()
            if os.path.isfile(path):
                logger.debug(f"CJK font via fc-match: {path}")
                return path
    except Exception:
        pass

    logger.warning("No CJK font found; subtitle text may not render correctly for Chinese")
    return None


# ── Color utilities ─────────────────────────────────────────────────────────

def _parse_hex_color(color: str) -> tuple[int, int, int]:
    """Parse '#RRGGBB' or 'RRGGBB' into (r, g, b) integers."""
    c = color.lstrip('#')
    if len(c) == 6:
        try:
            return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        except ValueError:
            pass
    return 255, 255, 255


# ── PIL subtitle clip ────────────────────────────────────────────────────────

def _make_subtitle_clip(
    text: str,
    video_w: int,
    video_h: int,
    font,
    font_size: int,
    color_rgb: tuple[int, int, int],
    duration: float,
    start_time: float,
    bottom_margin: int = 80,
):
    """
    Render a subtitle text block as a MoviePy ImageClip positioned at the
    bottom-center of the frame.
    """
    import numpy as np
    from PIL import Image, ImageDraw
    from moviepy.editor import ImageClip

    pad_x = 50
    pad_y = 18
    shadow_offset = 2
    line_gap = 8
    lines = text.split('\n')

    # Measure each line
    line_sizes: list[tuple[int, int]] = []
    for line in lines:
        if hasattr(font, 'getbbox'):
            bbox = font.getbbox(line)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        else:
            w, h = len(line) * font_size, font_size
        line_sizes.append((w, h))

    max_line_w = max((s[0] for s in line_sizes), default=font_size)
    total_line_h = sum(s[1] for s in line_sizes) + line_gap * max(len(lines) - 1, 0)

    box_w = min(max_line_w + 2 * pad_x, video_w - 40)
    box_h = total_line_h + 2 * pad_y

    # Transparent base + semi-opaque background
    base = Image.new('RGBA', (box_w, box_h), (0, 0, 0, 0))
    bg = Image.new('RGBA', (box_w, box_h), (0, 0, 0, 150))
    img = Image.alpha_composite(base, bg)
    draw = ImageDraw.Draw(img)

    y = pad_y
    for k, line in enumerate(lines):
        lw, lh = line_sizes[k]
        x = max((box_w - lw) // 2, 0)
        # Drop shadow
        draw.text((x + shadow_offset, y + shadow_offset), line, font=font, fill=(0, 0, 0, 200))
        # Main text
        draw.text((x, y), line, font=font, fill=(*color_rgb, 255))
        y += lh + line_gap

    clip = ImageClip(np.array(img), ismask=False)
    clip = clip.set_duration(duration).set_start(start_time)

    x_pos = (video_w - box_w) // 2
    y_pos = video_h - box_h - bottom_margin
    clip = clip.set_position((x_pos, y_pos))
    return clip


# ── Main overlay entry point ─────────────────────────────────────────────────

def add_subtitle_moviepy(
    video_path: str,
    narration: str,
    subtitle_config: dict,
    output_path: str,
) -> str:
    """
    Overlay timed subtitles on a video clip using MoviePy + PIL.

    Splits narration into display segments proportional to total duration.
    Each segment is rendered with PIL (no ImageMagick required) and composited
    over the video via MoviePy.

    Args:
        video_path: Input video file path
        narration: Full narration text for this segment
        subtitle_config: Dict with keys: color (hex), font_size (int), max_chars (int)
        output_path: Destination video file path

    Returns:
        output_path on success
    """
    from PIL import ImageFont
    from moviepy.editor import VideoFileClip, CompositeVideoClip

    font_size = int(subtitle_config.get('font_size', 40))
    color_hex = str(subtitle_config.get('color', '#FFFFFF'))
    max_chars = int(subtitle_config.get('max_chars', 16))
    color_rgb = _parse_hex_color(color_hex)
    font_path = find_cjk_font()

    segments = split_narration_to_segments(narration.strip(), max_chars, max_lines=2)

    # Load font
    if font_path and os.path.isfile(font_path):
        try:
            font = ImageFont.truetype(font_path, font_size)
        except Exception as e:
            logger.warning(f"Failed to load font {font_path}: {e}, using default")
            font = ImageFont.load_default()
    else:
        font = ImageFont.load_default()

    video = VideoFileClip(video_path)
    total_dur = video.duration
    n_segs = len(segments)
    seg_dur = total_dur / n_segs

    clips = [video]
    for i, seg_text in enumerate(segments):
        if not seg_text.strip():
            continue
        start = i * seg_dur
        end = min((i + 1) * seg_dur, total_dur)
        sub_clip = _make_subtitle_clip(
            text=seg_text,
            video_w=video.w,
            video_h=video.h,
            font=font,
            font_size=font_size,
            color_rgb=color_rgb,
            duration=end - start,
            start_time=start,
        )
        clips.append(sub_clip)

    result = CompositeVideoClip(clips)
    result.write_videofile(
        output_path,
        fps=video.fps,
        codec='libx264',
        audio_codec='aac',
        temp_audiofile=output_path + '.tmp.m4a',
        remove_temp=True,
        logger=None,
        preset='medium',
    )

    video.close()
    result.close()
    logger.debug(f"Subtitle overlay written: {output_path}")
    return output_path
