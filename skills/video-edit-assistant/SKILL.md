---
name: video-edit-assistant
description: 对话式收集视频自动剪辑参数，并在信息齐全时构造 Pixelle-Video scripted_asset_edit 请求。适用于用户直接提供文案、素材、TTS 参考音频、BGM 和剪辑说明的场景。
---

# Video Edit Assistant

这个 skill 用于把“自然语言视频制作需求”整理成结构化请求，供 Pixelle-Video 的 `scripted_asset_edit` pipeline 调用。

## 什么时候使用

当用户表达类似需求时使用：

- “帮我做一个视频，我来给文案和素材”
- “我有一段文案和几段视频，帮我自动剪辑”
- “我要做带配音和字幕的 demo 视频”
- “我有声音克隆音频，帮我合成一个短视频”

## 你的职责

1. 维护一个视频制作草稿（draft）
2. 识别缺失的关键字段
3. 一次最多追问 3 个问题
4. 信息齐全后输出可调用 `/api/video/scripted-asset-edit/sync` 的 payload

## 关键必填项

- `script_text`
- `asset_paths`
- `frame_template`（或由画幅映射）

## 推荐缺省值

- `split_mode=paragraph`
- `duration_target=30`
- `skip_asset_analysis=true`
- `subtitle_enabled=true`
- `pace=medium`
- `transition_style=simple`
- `source=selfhost`
- `frame_template=1080x1920/asset_default.html`

## 交互原则

- 如果用户已经给了文案，不要重复追问主题
- 如果用户已经给了素材，不要再要求 AI 自动生成素材
- 如果用户没有指定横竖版，优先追问画幅
- 如果用户要声音克隆，提醒其上传 mp3/wav 参考音频
- 如果必填信息已齐，优先生成 payload，不要继续无意义追问

## 仓库内参考实现

- `skills/video_edit_intake.py`
- `skills/video_edit_assistant_runtime.py`
- `skills/video_edit_assistant_adapter.py`
- `skills/video_edit_assistant_cli.py`

## 最小测试入口

你可以使用：

```bash
python3 skills/video_edit_assistant_cli.py --patch '{"project_name":"demo"}' --aspect-ratio 9:16 --pretty
```

或使用仓库内包装入口：

```bash
python3 skills/video-edit-assistant/run_skill.py --patch '{"project_name":"demo"}' --aspect-ratio 9:16 --pretty
```
