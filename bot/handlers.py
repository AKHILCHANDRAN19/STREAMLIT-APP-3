import asyncio
import os
import uuid
from bot.keyboards import (
    get_doctype_keyboard,
    get_processing_keyboard,
    get_split_keyboard,
)
from bot.pipeline import run_queue_pipeline
from bot.queue_manager import USER_QUEUE
from config import DOWNLOAD_DIR, OWNER_IDS
from pyrogram.types import CallbackQuery, Message
from utils.telemetry import GLOBAL_STATE

WELCOME_TEXT = (
    "🎯 **Welcome to the GenAI Processor Bot** 🎯\n\n"
    "Powered strictly by modern WebAPI sessions, PyMuPDF, and WeasyPrint.\n\n"
    "🤖 **Available Commands:**\n"
    "🔹 `/start` - View guide & reset state\n"
    "🔹 `/queue` - Check current queued files\n"
    "🔹 `/done` - Finalize queue & select action\n"
    "🔹 `/clear` - Empty current queue\n\n"
    "📥 **How to Use:**\n"
    "1️⃣ Send one or more `.pdf`, images, or `.txt` files.\n"
    "2️⃣ Type `/done` or `done`.\n"
    "3️⃣ Choose Pointwise, Chapter, or Smart Chapter Split."
)


def is_authorized(user_id: int) -> bool:
  return (not OWNER_IDS) or (user_id in OWNER_IDS)


async def log_incoming_messages(client, message: Message):
  user_info = f"User {message.from_user.id}" if message.from_user else "Unknown"
  desc = message.text or (
      f"[Media/File] {message.document.file_name}"
      if message.document
      else "[Media/File]"
  )
  GLOBAL_STATE.log(f"📩 Incoming: {desc} from {user_info}")
  try:
    message.continue_propagation()
  except Exception:
    pass


async def start_cmd(client, message: Message):
  user_id = message.from_user.id if message.from_user else 0
  if not is_authorized(user_id):
    return await message.reply_text("⚠️ **Unauthorized user ID.**")
  await message.reply_text(WELCOME_TEXT)


async def check_queue_cmd(client, message: Message):
  user_id = message.from_user.id if message.from_user else 0
  if not is_authorized(user_id):
    return

  files = USER_QUEUE.get_files(user_id)
  if not files:
    return await message.reply_text(
        "🫙 **Queue is empty.** Send files to begin."
    )

  text = f"📊 **Queue Status ({len(files)} files):**\n\n"
  for idx, f in enumerate(files, 1):
    text += f"{idx}. `{f['name']}`\n"

  doc_type = USER_QUEUE.get_doc_type(user_id)
  if not doc_type:
    text += "\n👉 Please select the document structure:"
    await message.reply_text(text, reply_markup=get_doctype_keyboard())
  elif doc_type == "split":
    text += (
        "\n📑 **Structure:** `✂️ Smart Split`\n\n👉 Click below to proceed:"
    )
    await message.reply_text(text, reply_markup=get_split_keyboard())
  else:
    doc_label = (
        "📌 Pointwise" if doc_type == "pointwise" else "📖 Chapter / Paragraph"
    )
    text += f"\n📑 **Structure:** `{doc_label}`\n\n👉 Select processing mode:"
    await message.reply_text(text, reply_markup=get_processing_keyboard())


async def done_cmd(client, message: Message):
  user_id = message.from_user.id if message.from_user else 0
  if not is_authorized(user_id):
    return

  files = USER_QUEUE.get_files(user_id)
  if not files:
    return await message.reply_text(
        "❌ Your queue is empty. Send some files first."
    )

  if USER_QUEUE.is_processing(user_id):
    return await message.reply_text(
        "⚠️ The bot is already processing your queue."
    )

  text = f"📊 **Queue Ready ({len(files)} files).**\n"
  doc_type = USER_QUEUE.get_doc_type(user_id)

  if not doc_type:
    text += "\n👉 Select document structure:"
    await message.reply_text(text, reply_markup=get_doctype_keyboard())
  elif doc_type == "split":
    text += "\n📑 **Structure:** `✂️ Smart Split`\n👉 Click below to run:"
    await message.reply_text(text, reply_markup=get_split_keyboard())
  else:
    doc_label = (
        "📌 Pointwise" if doc_type == "pointwise" else "📖 Chapter / Paragraph"
    )
    text += f"\n📑 **Structure:** `{doc_label}`\n👉 Select processing mode:"
    await message.reply_text(text, reply_markup=get_processing_keyboard())


async def clear_cmd(client, message: Message):
  user_id = message.from_user.id if message.from_user else 0
  if not is_authorized(user_id):
    return

  USER_QUEUE.clear_queue(user_id)
  await message.reply_text(
      "🗑️ **Queue cleared.** Temporary files removed from storage."
  )


async def handle_document(client, message: Message):
  user_id = message.from_user.id if message.from_user else 0
  if not is_authorized(user_id):
    return

  file_name = "unknown.pdf"
  if message.document:
    file_name = message.document.file_name or f"doc_{uuid.uuid4().hex[:6]}.pdf"
  elif message.photo:
    file_name = f"photo_{uuid.uuid4().hex[:6]}.jpg"

  if USER_QUEUE.is_processing(user_id):
    return await message.reply_text(
        "⚠️ Current batch is still processing. Please wait for completion."
    )

  status_msg = await message.reply_text("📥 **Downloading to local queue...**")
  dest_path = os.path.join(DOWNLOAD_DIR, f"{uuid.uuid4().hex[:6]}_{file_name}")
  await message.download(file_name=dest_path)

  # Registers the file into USER_QUEUE along with message.id for exact echoing
  USER_QUEUE.add_file(user_id, dest_path, file_name, message.id)

  q_len = len(USER_QUEUE.get_files(user_id))
  GLOBAL_STATE.log(
      f"Queued file: {file_name} for user {user_id} (Queue length: {q_len})"
  )

  base_text = (
      f"📥 **Added to Queue!**\n\n📁 **File:** `{file_name}`\n📊 **Queue"
      f" Size:** `{q_len}`\n\n"
  )
  doc_type = USER_QUEUE.get_doc_type(user_id)

  if not doc_type:
    await status_msg.edit_text(
        base_text + "👉 Select document structure:",
        reply_markup=get_doctype_keyboard(),
    )
  elif doc_type == "split":
    await status_msg.edit_text(
        base_text
        + "📑 **Structure:** `✂️ Smart Split`\n👉 Click below to proceed:",
        reply_markup=get_split_keyboard(),
    )
  else:
    doc_label = (
        "📌 Pointwise" if doc_type == "pointwise" else "📖 Chapter / Paragraph"
    )
    await status_msg.edit_text(
        base_text
        + f"📑 **Structure:** `{doc_label}`\n👉 Select processing mode:",
        reply_markup=get_processing_keyboard(),
    )


async def queue_callbacks(client, callback_query: CallbackQuery):
  user_id = callback_query.from_user.id
  if not is_authorized(user_id):
    return await callback_query.answer("⚠️ Unauthorized.", show_alert=True)

  data = callback_query.data

  if data == "clear_queue":
    USER_QUEUE.clear_queue(user_id)
    await callback_query.edit_message_text("🗑️ **Queue cleared successfully.**")
    return await callback_query.answer("Queue cleared")

  if not USER_QUEUE.get_files(user_id):
    return await callback_query.answer(
        "❌ Queue is empty or expired.", show_alert=True
    )

  if USER_QUEUE.is_processing(user_id):
    return await callback_query.answer(
        "⚠️ Batch currently active.", show_alert=True
    )

  if data.startswith("set_type_"):
    dtype = data.replace("set_type_", "")
    USER_QUEUE.set_doc_type(user_id, dtype)
    q_len = len(USER_QUEUE.get_files(user_id))

    if dtype == "split":
      await callback_query.edit_message_text(
          f"📊 **Queue Ready ({q_len} files)**\n📑 **Structure:** `✂️ Smart"
          " Chapter Split`\n\n👉 Click below to execute:",
          reply_markup=get_split_keyboard(),
      )
    else:
      label = "📌 Pointwise" if dtype == "pointwise" else "📖 Chapter"
      await callback_query.edit_message_text(
          f"📊 **Queue Ready ({q_len} files)**\n📑 **Structure:** `{label}`\n\n👉"
          " Select execution mode:",
          reply_markup=get_processing_keyboard(),
      )
    return

  # Direct execution: pipeline.py handles multi-PDF iteration, echoing, and success stickers
  mode = data.replace("run_queue_", "")
  USER_QUEUE.set_processing(user_id, True)
  await callback_query.answer("Processing started!")

  asyncio.create_task(
      run_queue_pipeline(client, callback_query.message, user_id, mode)
  )


# Explicit compatibility aliases for client.py
start_handler = start_cmd
queue_cmd = check_queue_cmd
clear_handler = clear_cmd
done_handler = done_cmd
pdf_handler = handle_document
document_receiver = handle_document
callback_handler = queue_callbacks
handle_callback = queue_callbacks

