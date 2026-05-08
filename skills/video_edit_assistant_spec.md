# Video Edit Assistant Skill Spec

## 目标

为 `scripted_asset_edit` pipeline 增加一层 **对话式参数收集层**，让用户可以通过自然语言逐步提供：

- 文案
- 素材文件
- TTS / 声音克隆配置
- BGM
- 剪辑要求
- 输出规格

最终将这些信息整理为一个结构化请求，调用：

- `POST /api/video/scripted-asset-edit/sync`

或后续的 async 版本。

---

## 核心职责

### Skill 负责
- 判断当前任务是否缺少必要参数
- 逐轮向用户追问缺失信息
- 维护一个结构化的草稿任务对象
- 在信息足够时，构造请求 payload 并调用后端 API

### Pipeline 负责
- 脚本拆分
- 素材匹配
- TTS
- 模板渲染
- 视频合成

---

## 最小交互流程

### 第 1 步：任务初始化
用户可能会这样说：

- 帮我做一个 45 秒竖屏视频
- 文案我给你，素材我也给你
- 配音用我提供的声音克隆
- 风格偏科技感

Skill 先建立一个任务草稿。

### 第 2 步：缺失项追问
按优先级检查：

1. `script_text`
2. `asset_paths`
3. `frame_template` / 画幅
4. 是否启用 TTS
5. 如启用 TTS，是否提供 `ref_audio` / `tts_workflow`
6. 是否加 BGM
7. `editing_instruction`

### 第 3 步：生成请求
当必要字段齐全后，组装 payload 调 API。

---

## 建议的最小必填字段

- `script_text`
- `asset_paths`
- `frame_template`（或由画幅映射）

## 推荐但可缺省字段

- `project_name`
- `duration_target`
- `tts_workflow`
- `ref_audio`
- `bgm_path`
- `editing_instruction`
- `pace`
- `transition_style`

---

## 默认值建议

```json
{
  "split_mode": "paragraph",
  "duration_target": 30,
  "skip_asset_analysis": true,
  "subtitle_enabled": true,
  "pace": "medium",
  "transition_style": "simple",
  "source": "selfhost",
  "frame_template": "1080x1920/asset_default.html",
  "tts_speed": 1.0,
  "bgm_volume": 0.2,
  "bgm_mode": "loop"
}
```

---

## 缺失项问询文案建议

### 缺文案
请把完整文案直接发我，我会按段落或句子帮你拆成视频场景。

### 缺素材
请把要参与剪辑的图片/视频素材发我；如果是多个文件，我会按顺序或后续规则匹配到文案场景。

### 缺画幅
你要竖屏、横屏还是方形？
- 竖屏：9:16
- 横屏：16:9
- 方形：1:1

### 缺 TTS 参考音频
如果你想做声音克隆，请发一段 mp3/wav 参考音频；如果不用克隆，也可以直接告诉我要不要系统默认音色。

### 缺剪辑说明
如果你对节奏、转场、重点表达有要求，可以直接告诉我，比如：
- 前 3 秒要抓人
- 中间强调卖点
- 结尾落品牌

---

## 输出目标

Skill 最终要生成一个标准化 payload，供后端接口调用。
