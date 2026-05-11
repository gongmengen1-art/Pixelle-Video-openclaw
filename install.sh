#!/usr/bin/env bash
# =============================================================================
# Pixelle-Video  ×  openclaw  video-edit skill 一键安装脚本
#
# 用法：
#   bash install.sh
#
# 完成后用户只需在 Telegram 发送 /video-edit <内容> 即可使用。
# =============================================================================

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── 颜色 ─────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[0;33m'
BLU='\033[0;34m'; CYN='\033[0;36m'; BLD='\033[1m'; RST='\033[0m'

info()    { echo -e "${BLU}[INFO]${RST}  $*"; }
ok()      { echo -e "${GRN}[OK]${RST}    $*"; }
warn()    { echo -e "${YLW}[WARN]${RST}  $*"; }
error()   { echo -e "${RED}[ERROR]${RST} $*" >&2; }
section() { echo -e "\n${BLD}${CYN}══ $* ══${RST}"; }
ask() {
  # ask <prompt> <default> → echoes the value entered (or default)
  local prompt="$1" default="$2"
  local value
  read -r -p "$(echo -e "${YLW}?${RST} ${prompt} [${GRN}${default}${RST}]: ")" value
  echo "${value:-$default}"
}
ask_required() {
  # ask_required <prompt> → loops until non-empty value is given
  local prompt="$1" value=""
  while [[ -z "$value" ]]; do
    read -r -p "$(echo -e "${YLW}?${RST} ${prompt}: ")" value
    [[ -z "$value" ]] && echo -e "${RED}  此项为必填，请重新输入${RST}"
  done
  echo "$value"
}
ask_secret() {
  local prompt="$1" value=""
  while [[ -z "$value" ]]; do
    read -r -s -p "$(echo -e "${YLW}?${RST} ${prompt}: ")" value
    echo ""
    [[ -z "$value" ]] && echo -e "${RED}  此项为必填，请重新输入${RST}"
  done
  echo "$value"
}

# ── 横幅 ─────────────────────────────────────────────────────────────────────
echo -e "${BLD}"
cat << 'EOF'
  ____  _          _ _         __     ___     _
 |  _ \(_)_  _____| | | ___   \ \   / (_) __| | ___  ___
 | |_) | \ \/ / _ \ | |/ _ \   \ \ / /| |/ _` |/ _ \/ _ \
 |  __/| |>  <  __/ | |  __/    \ V / | | (_| |  __/ (_) |
 |_|   |_/_/\_\___|_|_|\___|     \_/  |_|\__,_|\___|\___/

         ×  openclaw  video-edit  skill  安装脚本
EOF
echo -e "${RST}"
echo "安装目录：${SCRIPT_DIR}"
echo ""

# ── 0. 系统检查 ──────────────────────────────────────────────────────────────
section "系统检查"

OS="$(uname -s)"
ARCH="$(uname -m)"
info "OS: ${OS} / ARCH: ${ARCH}"

if [[ "$OS" == "Darwin" ]]; then
  PKG_INSTALL="brew install"
  PKG_CHECK="brew list"
elif command -v apt-get &>/dev/null; then
  PKG_INSTALL="sudo apt-get install -y"
  PKG_CHECK="dpkg -l"
elif command -v yum &>/dev/null; then
  PKG_INSTALL="sudo yum install -y"
  PKG_CHECK="rpm -q"
else
  warn "无法识别包管理器，系统依赖请手动安装 ffmpeg"
  PKG_INSTALL="echo 手动安装："
  PKG_CHECK="false"
fi

# ── 1. 安装 uv ───────────────────────────────────────────────────────────────
section "安装 uv（Python 包管理器）"

if command -v uv &>/dev/null; then
  ok "uv 已安装：$(uv --version)"
else
  info "正在安装 uv …"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  ok "uv 安装完成：$(uv --version)"
fi

# 确保 uv 在 PATH
export PATH="$HOME/.local/bin:$PATH"

# ── 2. 安装 ffmpeg ───────────────────────────────────────────────────────────
section "安装 ffmpeg"

if command -v ffmpeg &>/dev/null; then
  ok "ffmpeg 已安装：$(ffmpeg -version 2>&1 | head -1)"
else
  info "正在安装 ffmpeg …"
  $PKG_INSTALL ffmpeg
  ok "ffmpeg 安装完成"
fi

# ── 3. Python 依赖 ───────────────────────────────────────────────────────────
section "安装 Python 依赖（uv sync）"

uv sync --quiet
ok "Python 依赖安装完成"

# ── 4. Playwright Chromium ───────────────────────────────────────────────────
section "安装 Playwright Chromium（HTML 渲染）"

if uv run python3 -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    b.close()
" 2>/dev/null; then
  ok "Playwright Chromium 已就绪"
else
  info "正在安装 Chromium …"
  uv run playwright install chromium
  ok "Playwright Chromium 安装完成"
fi

# ── 5. 配置向导 ──────────────────────────────────────────────────────────────
section "配置向导（config.yaml）"

EXISTING_CONFIG="$SCRIPT_DIR/config.yaml"
if [[ -f "$EXISTING_CONFIG" ]]; then
  echo -e "${YLW}检测到已有 config.yaml${RST}"
  OVERWRITE=$(ask "是否重新配置？输入 yes 重新配置，否则跳过" "no")
  if [[ "$OVERWRITE" != "yes" ]]; then
    info "跳过配置向导，使用现有 config.yaml"
    # 仍然读取现有配置中的 API 端口
    API_PORT=$(uv run python3 -c "
import yaml, re, os
cfg = yaml.safe_load(open('config.yaml')) or {}
base = cfg.get('video_edit', {}).get('api_base', 'http://127.0.0.1:8011')
m = re.search(r':(\d+)$', base)
print(m.group(1) if m else '8011')
" 2>/dev/null || echo "8011")
    SKIP_CONFIG=true
  else
    SKIP_CONFIG=false
  fi
else
  SKIP_CONFIG=false
fi

if [[ "$SKIP_CONFIG" != "true" ]]; then
  echo ""
  echo "请依次填写以下配置项（必填项不可跳过）："
  echo ""

  # ── Pixelle-Video API ────────────────────────────────────────────────────
  echo -e "${BLD}▸ Pixelle-Video API${RST}"
  API_PORT=$(ask "API 端口" "8011")

  # ── OSS（必填）───────────────────────────────────────────────────────────
  echo ""
  echo -e "${BLD}▸ 阿里云 OSS（视频上传 / 公网访问，必填）${RST}"
  OSS_AK=$(ask_required     "AccessKey ID")
  OSS_SK=$(ask_secret       "AccessKey Secret")
  OSS_BUCKET=$(ask_required "Bucket 名称")
  OSS_ENDPOINT=$(ask        "Endpoint" "oss-accelerate.aliyuncs.com")
  OSS_PREFIX=$(ask          "Object Key 前缀" "openclaw/video-edit/")

  # ── 清理策略（可选）─────────────────────────────────────────────────────
  echo ""
  echo -e "${BLD}▸ 工作区自动清理${RST}"
  CLEANUP_TASK_HOURS=$(ask  "OSS 上传成功后保留本地文件的最长时间（小时，0=立即删除）" "0")
  CLEANUP_SESS_HOURS=$(ask  "Session 草稿过期时间（小时）" "168")

  # ── 写入 config.yaml ────────────────────────────────────────────────────
  info "正在写入 config.yaml …"
  uv run python3 - <<PYEOF
import yaml, os

# 如果存在旧配置则先读取（保留 llm / comfyui 等其他字段）
old = {}
if os.path.exists('config.yaml'):
    with open('config.yaml') as f:
        old = yaml.safe_load(f) or {}

cleanup_hours = float('${CLEANUP_TASK_HOURS}')
cfg = {
    'project_name': old.get('project_name', 'Pixelle-Video'),
    'llm': old.get('llm', {'api_key': '', 'base_url': '', 'model': ''}),
    'comfyui': old.get('comfyui', {
        'comfyui_url': 'http://127.0.0.1:8188',
        'comfyui_api_key': '',
        'runninghub_api_key': '',
        'runninghub_concurrent_limit': 1,
        'tts': {'default_workflow': 'selfhost/tts_edge.json'},
        'image': {'default_workflow': 'runninghub/image_flux.json'},
        'video': {'default_workflow': 'runninghub/video_wan2.1_fusionx.json'},
    }),
    'template': old.get('template', {'default_template': '1080x1920/image_default.html'}),
    'video_edit': {
        'api_base': f'http://127.0.0.1:${API_PORT}',
        'session_dir': '~/.openclaw/workspace/memory/video-edit-sessions',
        'output_base': '',
        'default_bgm': 'bgm/default.mp3',
        'cleanup': {
            'after_oss_upload': cleanup_hours == 0,
            'max_task_age_hours': int('${CLEANUP_TASK_HOURS}') if int('${CLEANUP_TASK_HOURS}') > 0 else 24,
            'max_session_age_hours': int('${CLEANUP_SESS_HOURS}'),
        },
        'oss': {
            'access_key_id': '${OSS_AK}',
            'access_key_secret': '${OSS_SK}',
            'bucket': '${OSS_BUCKET}',
            'endpoint': '${OSS_ENDPOINT}',
            'prefix': '${OSS_PREFIX}',
        },
    },
}

with open('config.yaml', 'w', encoding='utf-8') as f:
    yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
print('config.yaml 写入完成')
PYEOF
  ok "config.yaml 已生成"
fi

# ── 6. Systemd 服务（Pixelle-Video API）────────────────────────────────────
section "注册 Pixelle-Video API 系统服务"

SERVICE_NAME="pixelle-video-api"
UV_BIN="$(command -v uv || echo "$HOME/.local/bin/uv")"
CURRENT_USER="$(whoami)"

if command -v systemctl &>/dev/null && [[ "$OS" == "Linux" ]]; then
  SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
  info "生成 systemd 服务文件：${SERVICE_FILE}"

  sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=Pixelle-Video API Server (video-edit skill)
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${SCRIPT_DIR}
ExecStart=${UV_BIN} run python api/app.py --host 127.0.0.1 --port ${API_PORT}
Restart=always
RestartSec=5
Environment=PATH=${HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=multi-user.target
EOF

  sudo systemctl daemon-reload
  sudo systemctl enable --now "$SERVICE_NAME"
  sleep 3

  if systemctl is-active --quiet "$SERVICE_NAME"; then
    ok "systemd 服务 ${SERVICE_NAME} 已启动并设为开机自启"
  else
    warn "服务未能启动，查看日志：journalctl -u ${SERVICE_NAME} -n 50"
  fi

else
  # macOS / 无 systemd 环境：后台运行
  warn "当前环境无 systemd，以后台进程方式启动 API"
  pkill -f "python api/app.py" 2>/dev/null || true
  nohup uv run python api/app.py --host 127.0.0.1 --port "$API_PORT" \
    > /tmp/pixelle-video-api.log 2>&1 &
  ok "API 后台进程已启动（日志：/tmp/pixelle-video-api.log）"
  sleep 4
fi

# 健康检查
MAX_WAIT=30
WAITED=0
until curl -sf "http://127.0.0.1:${API_PORT}/health" &>/dev/null; do
  sleep 2; WAITED=$((WAITED+2))
  [[ $WAITED -ge $MAX_WAIT ]] && { error "API 启动超时，请手动检查"; break; }
done
ok "API 健康检查通过：http://127.0.0.1:${API_PORT}/health"

# ── 7. Cron 定时清理 ─────────────────────────────────────────────────────────
section "配置定时清理任务（cron）"

CLEANER="$SCRIPT_DIR/skills/video-edit-assistant/workspace_cleaner.py"
CRON_CMD="0 3 * * * cd ${SCRIPT_DIR} && ${UV_BIN} run python3 ${CLEANER} --max-task-age-hours 24 >> /tmp/pixelle-cleanup.log 2>&1"
CRON_MARKER="# pixelle-video-cleanup"

# 检查是否已存在
if crontab -l 2>/dev/null | grep -q "pixelle-video-cleanup"; then
  ok "定时清理任务已存在，跳过"
else
  (crontab -l 2>/dev/null; echo "$CRON_CMD  $CRON_MARKER") | crontab -
  ok "已添加每日 03:00 自动清理任务"
fi

# ── 8. openclaw Telegram 路由注册 ────────────────────────────────────────────
section "openclaw Telegram 路由接入"

ROUTE_SNIPPET_FILE="$SCRIPT_DIR/skills/video-edit-assistant/openclaw_integration_example.py"

cat > "$ROUTE_SNIPPET_FILE" << 'PYEOF'
"""
openclaw Telegram Bot 接入示例
将以下代码集成到 openclaw 的消息处理器中。

同步接入（适合 requests / threading 风格的 bot）：

    from skills.video-edit-assistant.openclaw_router import handle_telegram_update

    def on_message(update: dict, bot_token: str):
        result = handle_telegram_update(
            bot_token=bot_token,
            update=update,
            upload_oss=True,
        )
        if result:
            # result["reply_text"] 是要发给用户的消息
            # result["state"]      是 "collecting" 或 "executed"
            send_telegram_message(
                chat_id=update["message"]["chat"]["id"],
                text=result["reply_text"],
            )

异步接入（适合 aiogram / python-telegram-bot v20+ 风格的 bot）：

    from skills.video-edit-assistant.openclaw_router import handle_telegram_update_async

    async def on_message(update: dict, bot_token: str):
        result = await handle_telegram_update_async(
            bot_token=bot_token,
            update=update,
            upload_oss=True,
        )
        if result:
            await bot.send_message(
                chat_id=update["message"]["chat"]["id"],
                text=result["reply_text"],
            )

触发前缀（满足任意一个即路由到本 skill）：
    /video-edit
    video-edit:
    视频剪辑：

用户发送示例：
    /video-edit 帮我做个30秒竖屏产品介绍视频
    /video-edit 文案：产品功能强大，操作简单。
"""

# ── 如果 openclaw 使用 CLI 调用而非 Python import，可直接调用：
#
#   python3 skills/video-edit-assistant/route_video_edit_message.py \
#     --user-key "tg:{telegram_user_id}" \
#     --text "{raw_message_text}" \
#     --media "{downloaded_file_path_1}" \
#     --media "{downloaded_file_path_2}" \
#     --upload-oss
#
#   输出 JSON，取 reply_text 字段发送给用户。
PYEOF

ok "接入示例已写入：${ROUTE_SNIPPET_FILE}"

# ── 8.1 OpenClaw 原生 Telegram Router Extension ─────────────────────────────
# 将 /video-edit 消息在进入 LLM 前拦截，直接调用本 skill 的 CLI。
# 这一步是 OpenClaw 环境里的真正自动路由接入；上面的 Python 示例用于外部 Bot 手动集成。
OPENCLAW_WORKSPACE="${HOME}/.openclaw/workspace"
EXT_DIR="${OPENCLAW_WORKSPACE}/.openclaw/extensions/video-edit-router"
SKILL_LINK_DIR="${HOME}/.agents/skills"
SKILL_LINK="${SKILL_LINK_DIR}/video-edit-assistant"
PYTHON_BIN="${SCRIPT_DIR}/.venv/bin/python"
ROUTE_SCRIPT="${SCRIPT_DIR}/skills/video-edit-assistant/route_video_edit_message.py"
SESSION_DIR="${OPENCLAW_WORKSPACE}/memory/video-edit-sessions"

mkdir -p "${EXT_DIR}" "${SKILL_LINK_DIR}" "${SESSION_DIR}"
ln -sfn "${SCRIPT_DIR}/skills/video-edit-assistant" "${SKILL_LINK}"

cat > "${EXT_DIR}/package.json" <<'EOF'
{
  "name": "video-edit-router",
  "version": "0.2.0",
  "type": "module",
  "openclaw": {
    "extensions": ["./index.js"]
  }
}
EOF

cat > "${EXT_DIR}/openclaw.plugin.json" <<EOF
{
  "id": "video-edit-router",
  "name": "Video Edit Telegram Router",
  "version": "0.2.0",
  "description": "Claims Telegram /video-edit conversations and routes them to the Pixelle-Video bridge.",
  "entry": "./index.js",
  "enabled": true,
  "config": {
    "python": "${PYTHON_BIN}",
    "script": "${ROUTE_SCRIPT}",
    "cwd": "${SCRIPT_DIR}",
    "apiBase": "http://127.0.0.1:${API_PORT}",
    "uploadOss": true,
    "sessionDir": "${SESSION_DIR}"
  },
  "configSchema": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "enabled": { "type": "boolean" },
      "python": { "type": "string" },
      "script": { "type": "string" },
      "cwd": { "type": "string" },
      "apiBase": { "type": "string" },
      "uploadOss": { "type": "boolean" },
      "sessionDir": { "type": "string" }
    }
  }
}
EOF

cat > "${EXT_DIR}/index.js" <<EOF
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { existsSync } from "node:fs";
import { readdir } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

const DEFAULT_PYTHON = ${PYTHON_BIN@Q};
const DEFAULT_SCRIPT = ${ROUTE_SCRIPT@Q};
const DEFAULT_CWD = ${SCRIPT_DIR@Q};
const DEFAULT_API_BASE = "http://127.0.0.1:${API_PORT}";
const DEFAULT_SESSION_DIR = ${SESSION_DIR@Q};
const TRIGGERS = ["/video-edit", "/video_edit", "video-edit:", "视频剪辑："];
const COMMAND_ALIASES = ["video_edit", "video_edit_assistant"];
const MEDIA_EXT = /\\.(mp4|mov|m4v|webm|avi|mkv|jpg|jpeg|png|webp|gif|wav|mp3|m4a)$/i;
const LOCAL_MEDIA_RE = /(?:file:\\/\\/)?(\\/[\\S'"<>]+\\.(?:mp4|mov|m4v|webm|avi|mkv|jpg|jpeg|png|webp|gif|wav|mp3|m4a))/gi;

function textOf(event) {
  return String(event.bodyForAgent || event.body || event.transcript || event.content || "").trim();
}

function normalizeSender(senderId) {
  const raw = String(senderId || "current");
  return raw.replace(/^telegram:/, "").replace(/^tg:/, "");
}

function userKey(event, ctx) {
  return "tg:" + normalizeSender(event.senderId || ctx.senderId || ctx.from);
}

function hasTrigger(text) {
  const s = String(text || "").trim();
  return TRIGGERS.some((prefix) => s.startsWith(prefix));
}

function collectStrings(value, out = []) {
  if (typeof value === "string") out.push(value);
  else if (Array.isArray(value)) for (const item of value) collectStrings(item, out);
  else if (value && typeof value === "object") for (const item of Object.values(value)) collectStrings(item, out);
  return out;
}

function collectMediaPaths(event) {
  const seen = new Set();
  const candidates = [];
  for (const s of collectStrings(event)) {
    if (MEDIA_EXT.test(s) && existsSync(s.replace(/^file:\\/\\//, ""))) candidates.push(s.replace(/^file:\\/\\//, ""));
    for (const match of s.matchAll(LOCAL_MEDIA_RE)) candidates.push(match[1]);
  }
  return candidates.filter((p) => {
    if (seen.has(p) || !existsSync(p)) return false;
    seen.add(p);
    return true;
  });
}

async function hasDraft(sessionDir, key) {
  const bareKey = String(key).replace(/^tg:/, "telegram-").replace(/^telegram:/, "telegram-");
  const safeKey = String(key).replace(/[^a-zA-Z0-9_.-]/g, "_");
  const names = [key + ".json", safeKey + ".json", bareKey + ".json"];
  try {
    const entries = await readdir(sessionDir);
    return names.some((name) => entries.includes(name));
  } catch {
    return false;
  }
}

function pluginConfigFromCommand(ctx) {
  return ctx?.config?.plugins?.entries?.["video-edit-router"]?.config || {};
}

function resolvedConfig(raw = {}) {
  return {
    python: String(raw.python || DEFAULT_PYTHON),
    script: String(raw.script || DEFAULT_SCRIPT),
    cwd: String(raw.cwd || DEFAULT_CWD),
    apiBase: String(raw.apiBase || DEFAULT_API_BASE),
    uploadOss: raw.uploadOss !== false,
    sessionDir: String(raw.sessionDir || DEFAULT_SESSION_DIR),
  };
}

async function runBridge({ python, script, cwd, apiBase, uploadOss, sessionDir, key, text, media }) {
  const args = [script, "--user-key", key, "--text", text, "--api-base", apiBase, "--pretty"];
  if (uploadOss) args.push("--upload-oss");
  for (const path of media) args.push("--media", path);

  const { stdout } = await execFileAsync(python, args, {
    cwd,
    env: { ...process.env, VIDEO_EDIT_SESSION_DIR: sessionDir },
    maxBuffer: 20 * 1024 * 1024,
    timeout: 20 * 60 * 1000,
  });
  return JSON.parse(stdout);
}

async function runCommandBridge(ctx, commandText) {
  const cfg = resolvedConfig(pluginConfigFromCommand(ctx));
  const key = "tg:" + normalizeSender(ctx.senderId || ctx.from);
  const result = await runBridge({ ...cfg, key, text: commandText, media: [] });
  return { text: result.reply_text || JSON.stringify(result) };
}

function commandDef(name, nativeName = name.replaceAll("-", "_")) {
  return {
    name,
    nativeNames: { default: nativeName },
    nativeProgressMessages: { default: "处理中..." },
    description: "进入 Pixelle-Video 多轮自动剪辑流程",
    channels: ["telegram"],
    acceptsArgs: true,
    requireAuth: true,
    async handler(ctx) {
      try {
        const commandText = "/video-edit" + (ctx.args ? " " + ctx.args : "");
        return await runCommandBridge(ctx, commandText);
      } catch (error) {
        return { text: "视频剪辑桥接执行失败：" + (error?.message || String(error)), isError: true };
      }
    },
  };
}

export default definePluginEntry({
  id: "video-edit-router",
  name: "Video Edit Telegram Router",
  description: "Routes Telegram /video-edit turns into Pixelle-Video without invoking the LLM.",
  register(api) {
    for (const alias of COMMAND_ALIASES) api.registerCommand(commandDef(alias, alias));

    api.on("inbound_claim", async (event, ctx) => {
      const rawCfg = event.context?.pluginConfig || ctx.pluginConfig || {};
      if (rawCfg.enabled === false) return;
      if (event.channel !== "telegram") return;

      const text = textOf(event);
      const cfg = resolvedConfig(rawCfg);
      const key = userKey(event, ctx);
      const shouldHandle = hasTrigger(text) || await hasDraft(cfg.sessionDir, key);
      if (!shouldHandle) return;

      try {
        const result = await runBridge({ ...cfg, key, text, media: collectMediaPaths(event) });
        return {
          handled: true,
          reply: {
            text: result.reply_text || JSON.stringify(result),
            replyToId: event.messageId ? String(event.messageId) : undefined,
          },
        };
      } catch (error) {
        return {
          handled: true,
          reply: {
            text: "视频剪辑桥接执行失败：" + (error?.message || String(error)),
            replyToId: event.messageId ? String(event.messageId) : undefined,
            isError: true,
          },
        };
      }
    }, { priority: 100, timeoutMs: 600000 });
  },
});
EOF

node --check "${EXT_DIR}/index.js"
ok "OpenClaw Telegram router extension 已安装：${EXT_DIR}"
ok "Skill symlink 已安装：${SKILL_LINK}"

# 将 workspace extension 安装/刷新到 OpenClaw 全局插件目录，确保 gateway 能发现并加载。
if command -v openclaw >/dev/null 2>&1; then
  info "正在安装/刷新 OpenClaw video-edit-router 插件…"
  if openclaw plugins install --force "${EXT_DIR}" >/tmp/video-edit-router-plugin-install.log 2>&1; then
    ok "OpenClaw 插件已安装/刷新：video-edit-router"
  else
    warn "OpenClaw 插件安装命令失败，请检查 /tmp/video-edit-router-plugin-install.log"
  fi
else
  warn "未找到 openclaw CLI，跳过插件全局安装"
fi

# Telegram Bot 菜单命令注册。
# 注意：Telegram Bot API 不允许命令名包含连字符，所以 /video-edit 不能出现在菜单中；
# 这里注册合法的 /video_edit，并且 router 同时兼容用户手动输入 /video-edit。
section "注册 Telegram Bot 指令菜单"
python3 - <<'PYEOF'
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

config_path = Path.home() / ".openclaw" / "openclaw.json"
token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
if not token and config_path.exists():
    try:
        cfg = json.loads(config_path.read_text())
        token = str(((cfg.get("channels") or {}).get("telegram") or {}).get("botToken") or "").strip()
    except Exception as exc:
        print(f"WARN: 读取 OpenClaw Telegram 配置失败：{exc}", file=sys.stderr)

if not token:
    print("WARN: 未找到 Telegram bot token，跳过 setMyCommands", file=sys.stderr)
    sys.exit(0)

commands = [
    {
        "command": "video_edit",
        "description": "进入 Pixelle-Video 自动剪辑流程",
    }
]
payload = json.dumps({"commands": commands, "scope": {"type": "default"}}, ensure_ascii=False).encode("utf-8")
req = urllib.request.Request(
    f"https://api.telegram.org/bot{token}/setMyCommands",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if body.get("ok"):
        print("OK: Telegram Bot 菜单命令已注册：/video_edit")
    else:
        print("WARN: Telegram setMyCommands 返回失败：" + json.dumps(body, ensure_ascii=False), file=sys.stderr)
except urllib.error.HTTPError as exc:
    detail = exc.read().decode("utf-8", "replace")
    print(f"WARN: Telegram setMyCommands HTTP {exc.code}: {detail}", file=sys.stderr)
except Exception as exc:
    print(f"WARN: Telegram setMyCommands 失败：{exc}", file=sys.stderr)
PYEOF


# ── 9. 端到端冒烟测试 ────────────────────────────────────────────────────────
section "端到端冒烟测试"

DEMO_ASSET="$SCRIPT_DIR/demo-output/demo-min-real.mp4"
if [[ ! -f "$DEMO_ASSET" ]]; then
  warn "找不到演示素材 ${DEMO_ASSET}，跳过冒烟测试"
else
  info "正在运行冒烟测试（单轮，带 OSS 上传）…"
  if uv run python3 skills/video-edit-assistant/e2e_test.py \
       --asset "$DEMO_ASSET" \
       --text "安装验证视频，请忽略。" \
       --skill-mode quick_create 2>&1 | grep -E "PASS|FAIL|OSS|error"; then
    ok "冒烟测试完成"
  else
    warn "冒烟测试输出异常，请手动检查"
  fi
fi

# ── 10. 完成摘要 ─────────────────────────────────────────────────────────────
section "安装完成"

echo ""
echo -e "${BLD}${GRN}✅ Pixelle-Video × openclaw video-edit skill 安装成功${RST}"
echo ""
echo -e "  API 地址   : ${CYN}http://127.0.0.1:${API_PORT}${RST}"
echo -e "  API 文档   : ${CYN}http://127.0.0.1:${API_PORT}/docs${RST}"
echo -e "  配置文件   : ${CYN}${SCRIPT_DIR}/config.yaml${RST}"
echo -e "  清理日志   : ${CYN}/tmp/pixelle-cleanup.log${RST}"
echo ""
echo -e "${BLD}openclaw 路由接入：${RST}"
echo -e "  原生 Telegram router extension 已自动安装：${CYN}${EXT_DIR}${RST}"
echo -e "  Skill symlink：${CYN}${SKILL_LINK}${RST}"
echo -e "  外部 Bot 手动接入示例：${CYN}${ROUTE_SNIPPET_FILE}${RST}"
echo ""
echo -e "${BLD}Telegram 验证方式：${RST}"
echo -e "  在 Telegram 向 Bot 发送："
echo -e "  ${GRN}/video-edit 帮我做个30秒竖屏产品介绍视频${RST}"
echo -e "  Bot 应回复追问缺少的信息（文案 / 素材 / 画幅）"
echo ""
if command -v systemctl &>/dev/null && [[ "$OS" == "Linux" ]]; then
  echo -e "  查看 API 日志：${CYN}journalctl -u ${SERVICE_NAME} -f${RST}"
fi
echo ""
