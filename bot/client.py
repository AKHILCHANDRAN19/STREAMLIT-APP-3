import logging
from bot.handlers import (
    check_queue_cmd,
    clear_cmd,
    done_cmd,
    handle_document,
    handle_pattern_text,
    log_incoming_messages,
    queue_callbacks,
    start_cmd,
)
from config import API_HASH, API_ID, BOT_SESSION, BOT_TOKEN
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.handlers import CallbackQueryHandler, MessageHandler

logger = logging.getLogger("Telegram_Client_Builder")


def build_telegram_client() -> Client:
  common_args = {
      "name": "GenAI_Processor_Bot",
      "api_id": API_ID,
      "api_hash": API_HASH,
      "in_memory": True,
      "parse_mode": ParseMode.MARKDOWN,
      "workers": 4,
      "max_concurrent_transmissions": 1,
  }

  if BOT_SESSION:
    logger.info("Initializing Pyrofork client with BOT_SESSION string...")
    app = Client(session_string=BOT_SESSION, **common_args)
  else:
    logger.info("Initializing Pyrofork client with BOT_TOKEN...")
    app = Client(bot_token=BOT_TOKEN, **common_args)

  # Handlers
  app.add_handler(MessageHandler(log_incoming_messages), group=-1)
  app.add_handler(MessageHandler(start_cmd, filters.command("start")))
  app.add_handler(MessageHandler(check_queue_cmd, filters.command("queue")))
  app.add_handler(
      MessageHandler(
          done_cmd, filters.command("done") | filters.regex(r"^(done|Done)$")
      )
  )
  app.add_handler(
      MessageHandler(
          clear_cmd, filters.command("clear") | filters.regex(r"^(clear|Clear)$")
      )
  )
  app.add_handler(
      MessageHandler(handle_document, filters.document | filters.photo)
  )

  # 🆕 Listen for pattern inputs (excluding command keywords)
  app.add_handler(
      MessageHandler(
          handle_pattern_text,
          filters.text
          & ~filters.command(["start", "queue", "done", "clear"])
          & ~filters.regex(r"^(done|Done|clear|Clear)$"),
      )
  )

  # 🆕 Allows both existing run_queue callbacks and new tool callbacks
  app.add_handler(CallbackQueryHandler(queue_callbacks))

  return app
