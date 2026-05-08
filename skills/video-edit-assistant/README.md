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
