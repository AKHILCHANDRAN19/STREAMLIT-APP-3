import logging
from bot.handlers import (
    check_queue_cmd,
    clear_cmd,
    done_cmd,
    handle_document,
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
  """Configures client with single-stream transmission to avoid Python 3.12 socket collisions."""
  common_args = {
      "name": "GenAI_Processor_Bot",
      "api_id": API_ID,
      "api_hash": API_HASH,
      "in_memory": True,
      "parse_mode": ParseMode.MARKDOWN,
      "workers": 4,
      "max_concurrent_transmissions": 1,  # CRITICAL: Fixes 'call_exception_handler' socket crash
  }

  if BOT_SESSION:
    logger.info("Initializing Pyrofork client with BOT_SESSION string...")
    app = Client(session_string=BOT_SESSION, **common_args)
  else:
    logger.info("Initializing Pyrofork client with BOT_TOKEN...")
    app = Client(bot_token=BOT_TOKEN, **common_args)

  # Attach Handlers
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
  app.add_handler(
      CallbackQueryHandler(
          queue_callbacks,
          filters.regex(
              r"^(run_queue_mcq_gem|run_queue_text_gem|run_queue_both_gem|clear_queue|set_type_pointwise|set_type_chapter|set_type_split|run_queue_split)$"
          ),
      )
  )

  return app
