# video-edit-assistant

这是仓库内安装版的 skill 目录。

## 作用

把用户的自然语言视频制作需求整理成结构化请求，最终对接：

- `POST /api/video/scripted-asset-edit/sync`

## 目录说明

- `SKILL.md`：skill 行为说明
- `run_skill.py`：最小 CLI 入口，转调上层已实现的 adapter/runtime

## 最小示例

```bash
python3 skills/video-edit-assistant/run_skill.py \
  --patch '{"project_name":"brand-demo"}' \
  --aspect-ratio 9:16 \
  --pretty
```

如果补齐文案与素材：

```bash
python3 skills/video-edit-assistant/run_skill.py \
  --patch '{"project_name":"brand-demo","script_text":"第一段\\n第二段","asset_paths":["/tmp/a.mp4","/tmp/b.mp4"]}' \
  --aspect-ratio 9:16 \
  --pretty
```

如果本地 API 已启动，还可以直接执行闭环生成：

```bash
python3 skills/video-edit-assistant/run_skill.py \
  --patch '{"project_name":"brand-demo","script_text":"第一段\\n第二段","asset_paths":["/tmp/a.mp4","/tmp/b.mp4"]}' \
  --aspect-ratio 9:16 \
  --execute \
  --pretty
```

如果你要模拟 Telegram 多轮 `/video-edit` 场景，可以使用桥接入口：

```bash
python3 skills/video-edit-assistant/telegram_bridge_cli.py \
  --user-key telegram-7217243523 \
  --patch '{"project_name":"产品介绍视频"}' \
  --aspect-ratio 9:16 \
  --pretty
```

后续继续补第二轮、第三轮 patch 即可；当必填信息齐全时，会自动执行，并且如果带上 `--upload-oss` 会直接返回 OSS 链接。
