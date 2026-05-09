---
name: video-edit-assistant
description: 对话式收集视频自动剪辑参数，并在信息齐全时构造 Pixelle-Video scripted_asset_edit 请求。适用于用户直接提供文案、素材、TTS 参考音频、BGM 和剪辑说明的场景。
triggers:
  - /video-edit
  - "video-edit:"
  - "视频剪辑："
---

# Video Edit Assistant

这个 skill 用于把"自然语言视频制作需求"整理成结构化请求，供 Pixelle-Video 的 `scripted_asset_edit` pipeline 调用。

## openclaw 路由接入规范

### 触发条件

消息文本以下列任意前缀开头时路由到本 skill：

| 前缀 | 示例 |
|------|------|
| `/video-edit` | `/video-edit 帮我做一个30秒竖屏产品介绍` |
| `video-edit:` | `video-edit: 文案：产品功能介绍` |
| `视频剪辑：` | `视频剪辑：帮我做一个横屏视频` |

### openclaw 调用方式

当收到匹配消息时，openclaw 调用：

```bash
python3 /path/to/skills/video-edit-assistant/route_video_edit_message.py \
  --user-key "tg:{telegram_user_id}" \
  --text "{raw_message_text}" \
  [--media "{downloaded_media_path}"] \   # 每个附件文件各一个 --media
  --upload-oss \
  --api-base "http://127.0.0.1:8011"
```

### 返回格式

脚本输出 JSON，`reply_text` 字段即发送给用户的 Telegram 消息：

```json
{
  "state": "collecting | executed",
  "reply_text": "已进入视频剪辑收集模式。\n还缺这些关键项...",
  "execution": {
    "oss": { "url": "https://..." }
  }
}
```

openclaw 读取 `reply_text` 并通过 Bot API 回复用户。

### 素材文件处理

用户在 Telegram 发送图片/视频时，openclaw 应先将文件下载到本地临时目录，再通过 `--media` 参数传入。每个文件单独一个 `--media` 参数：

```bash
... --media /tmp/tg_media/photo_001.jpg --media /tmp/tg_media/video_002.mp4
```

### 会话持久化

每个用户的对话状态存储在 `session_dir`（默认 `~/.openclaw/workspace/memory/video-edit-sessions/{user_key}.json`），openclaw 无需额外管理，script 自动处理多轮。

---

## 什么时候使用

当用户表达类似需求时使用：

- "帮我做一个视频，我来给文案和素材"
- "我有一段文案和几段视频，帮我自动剪辑"
- "我要做带配音和字幕的 demo 视频"
- "我有声音克隆音频，帮我合成一个短视频"

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

## 本地测试入口

```bash
# 直接路由一条消息（等价于 openclaw 调用）
python3 skills/video-edit-assistant/route_video_edit_message.py \
  --user-key "tg:12345678" \
  --text "/video-edit 帮我做个竖屏视频，文案：测试产品介绍" \
  --upload-oss --pretty

# 端到端完整链路测试
python3 skills/video-edit-assistant/e2e_test.py \
  --asset /path/to/asset.jpg --mode both
```

## 仓库内参考实现

- `skills/video_edit_intake.py` — intake 状态机核心
- `skills/video_edit_assistant_runtime.py` — 对话编排层
- `skills/video_edit_assistant_adapter.py` — 无状态适配器
- `skills/video-edit-assistant/session_bridge.py` — 多轮会话持久化
- `skills/video-edit-assistant/message_bridge.py` — 消息解析 + 执行
- `skills/video-edit-assistant/upload_to_oss.py` — OSS 上传
