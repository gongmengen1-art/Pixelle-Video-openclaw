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
