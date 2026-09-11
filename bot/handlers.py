import asyncio
import logging
import os
import shutil
from config import DOWNLOAD_DIR, FONT_PATH, OWNER_IDS, TARGET_CHANNEL_ID
from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from services.gemini_service import (
    analyze_document_title,
    extract_table_of_contents,
    extract_text_and_tables_webapi,
    generate_mcqs_for_page,
    init_gemini_client,
    verify_chapter_page,
)
from utils.telemetry import GLOBAL_STATE

logger = logging.getLogger("Bot_Handlers")

SUCCESS_STICKER_ID = (
    "CAACAgIAAxkBAAFDtjVpptva4k-to_n8BKzQg23QeMvSTQACVgADRA3PFxlBkhksr1N3OgQ"
)

# User session queue: user_id -> list of queued file dictionaries
USER_QUEUES = {}


def get_user_queue(user_id: int) -> list:
  if user_id not in USER_QUEUES:
    USER_QUEUES[user_id] = []
  return USER_QUEUES[user_id]


# ==========================================
# 📡 0. TELEMETRY MESSAGE LOGGER (REQUIRED BY client.py)
# ==========================================
async def log_incoming_messages(client: Client, message: Message):
  """Intercepts and logs every incoming update to terminal and GLOBAL_STATE."""
  if not message or not message.from_user:
    return

  user_id = message.from_user.id
  if message.text:
    desc = message.text
  elif message.document:
    desc = f"[Media/File] {message.document.file_name or ''}".strip()
  elif message.photo:
    desc = "[Photo]"
  else:
    desc = "[Media/File]"

  log_entry = f"📩 Incoming: {desc} from User {user_id}"
  GLOBAL_STATE.log(log_entry)
  print(f"[{log_entry}]", flush=True)

  try:
    message.continue_propagation()
  except Exception:
    pass


# ==========================================
# 📥 1. COMMAND HANDLERS (EXACT NAMES FOR client.py)
# ==========================================
async def start_cmd(client: Client, message: Message):
  USER_QUEUES[message.from_user.id] = []
  welcome_text = (
      "👋 **Welcome to GenAI Document & MCQ Engine**\n\n"
      "**Available Commands:**\n"
      "🔹 Send one or more `.pdf` files.\n"
      "🔹 `/queue` - Check current queued files.\n"
      "🔹 `/done` - Finalize queue & select processing action.\n"
      "🔹 `/clear` - Empty current queue."
  )
  await message.reply_text(welcome_text)


async def check_queue_cmd(client: Client, message: Message):
  queue = get_user_queue(message.from_user.id)
  if not queue:
    await message.reply_text("📭 Your queue is currently empty.")
    return

  lines = [f"📂 **Queued Files ({len(queue)}):**"]
  for idx, item in enumerate(queue, 1):
    lines.append(f"{idx}. `{item['file_name']}`")
  await message.reply_text("\n".join(lines))


async def clear_cmd(client: Client, message: Message):
  USER_QUEUES[message.from_user.id] = []
  await message.reply_text("🗑 **Queue cleared successfully.**")


async def done_cmd(client: Client, message: Message):
  queue = get_user_queue(message.from_user.id)
  if not queue:
    await message.reply_text(
        "📭 Queue is empty. Send at least one PDF file first."
    )
    return

  keyboard = InlineKeyboardMarkup([
      [
          InlineKeyboardButton("✂️ Chapter Split", callback_data="mode_split"),
          InlineKeyboardButton("📝 Generate MCQs", callback_data="mode_mcq"),
      ],
      [
          InlineKeyboardButton(
              "📖 Text Extraction", callback_data="mode_extract"
          ),
          InlineKeyboardButton(
              "⚡ Both (MCQ + Text)", callback_data="mode_both"
          ),
      ],
      [InlineKeyboardButton("❌ Cancel", callback_data="mode_cancel")],
  ])

  await message.reply_text(
      f"📋 **{len(queue)} file(s) ready for processing.**\nSelect the action"
      " you wish to run:",
      reply_markup=keyboard,
  )


# ==========================================
# 📄 2. DOCUMENT INGESTION
# ==========================================
async def pdf_handler(client: Client, message: Message):
  if OWNER_IDS and message.from_user.id not in OWNER_IDS:
    await message.reply_text("⛔ You are not authorized to use this bot.")
    return

  doc = message.document
  if not doc or not doc.file_name or not doc.file_name.lower().endswith(".pdf"):
    await message.reply_text("⚠️ Please send only valid `.pdf` documents.")
    return

  queue = get_user_queue(message.from_user.id)
  queue.append({
      "file_id": doc.file_id,
      "file_name": doc.file_name,
      "caption": message.caption or "",
      "file_size": doc.file_size,
  })

  GLOBAL_STATE.log(
      f"Queued file: {doc.file_name} for user {message.from_user.id} (Queue"
      f" length: {len(queue)})"
  )
  await message.reply_text(
      f"📥 **Queued:** `{doc.file_name}`\nQueue length: **{len(queue)}**\nSend"
      " more files or type `/done` to proceed."
  )


# ==========================================
# 🚀 3. CALLBACK QUERY DISPATCHER
# ==========================================
async def callback_handler(client: Client, query: CallbackQuery):
  mode = query.data.replace("mode_", "")
  user_id = query.from_user.id
  chat_id = query.message.chat.id

  if mode == "cancel":
    USER_QUEUES[user_id] = []
    await query.message.edit_text("❌ Operation canceled and queue cleared.")
    return

  queue = list(get_user_queue(user_id))
  USER_QUEUES[user_id] = []
  await query.message.delete()

  if not queue:
    await client.send_message(chat_id, "📭 Queue was empty.")
    return

  status_msg = await client.send_message(
      chat_id,
      f"🏁 **Starting batch of {len(queue)} file(s) in {mode.upper()} mode...**",
  )

  for idx, item in enumerate(queue, 1):
    file_name = item["file_name"]
    original_caption = item["caption"]
    local_pdf_path = os.path.join(DOWNLOAD_DIR, file_name)

    try:
      # Step 1: Download the source PDF
      await status_msg.edit_text(
          f"⏳ **[{idx}/{len(queue)}] Downloading:** `{file_name}`..."
      )
      await client.download_media(
          message=item["file_id"], file_name=local_pdf_path
      )

      # Step 2: Send back source PDF with exact filename and original caption
      await client.send_document(
          chat_id=chat_id,
          document=local_pdf_path,
          file_name=file_name,
          caption=original_caption if original_caption else None,
      )

      # Step 3: Run processing mode
      if mode == "split":
        await execute_chapter_split(
            client, chat_id, local_pdf_path, file_name, status_msg
        )
      elif mode == "mcq":
        await execute_mcq_generation(
            client, chat_id, local_pdf_path, file_name, status_msg
        )
      elif mode == "extract":
        await execute_text_extraction(
            client, chat_id, local_pdf_path, file_name, status_msg
        )
      elif mode == "both":
        await execute_text_extraction(
            client, chat_id, local_pdf_path, file_name, status_msg
        )
        await execute_mcq_generation(
            client, chat_id, local_pdf_path, file_name, status_msg
        )

      # Step 4: Send success sticker boundary for this completed file
      try:
        await client.send_sticker(chat_id=chat_id, sticker=SUCCESS_STICKER_ID)
      except Exception as sticker_err:
        logger.warning(f"Could not send success sticker: {sticker_err}")

    except Exception as e:
      logger.error(f"Pipeline error on file {file_name}: {e}")
      await client.send_message(
          chat_id, f"❌ **Error processing `{file_name}`:**\n`{e}`"
      )
    finally:
      if os.path.exists(local_pdf_path):
        os.remove(local_pdf_path)

  await status_msg.delete()
  await client.send_message(
      chat_id, f"✅ **All {len(queue)} file(s) completed successfully!**"
  )


# ==========================================
# ✂️ SUBROUTINE: CHAPTER SPLIT
# ==========================================
async def execute_chapter_split(
    client: Client,
    chat_id: int,
    pdf_path: str,
    file_name: str,
    status_msg: Message,
):
  import pymupdf

  await status_msg.edit_text(f"✂️ **Splitting chapters for:** `{file_name}`...")
  gemini_client = await init_gemini_client()
  chat = gemini_client.start_chat(model="gemini-flash-lite")

  temp_preview_dir = os.path.join(DOWNLOAD_DIR, "previews")
  os.makedirs(temp_preview_dir, exist_ok=True)
  preview_imgs = []

  try:
    with pymupdf.open(pdf_path) as doc:
      max_preview = min(15, len(doc))
      for p_idx in range(max_preview):
        img_p = os.path.join(temp_preview_dir, f"prev_{p_idx}.png")
        doc[p_idx].get_pixmap(dpi=150).save(img_p)
        preview_imgs.append(img_p)

    toc_data = await extract_table_of_contents(chat, preview_imgs)
    offset = toc_data.offset

    await status_msg.edit_text(
        f"🔍 **Step 2: Visually verifying {len(toc_data.chapters)} chapter"
        " starts...**"
    )

    with pymupdf.open(pdf_path) as doc:
      total_p = len(doc)
      for i, chap in enumerate(toc_data.chapters):
        start_p = max(0, chap.printed_page + offset)
        if i + 1 < len(toc_data.chapters):
          end_p = min(total_p, toc_data.chapters[i + 1].printed_page + offset)
        else:
          end_p = total_p

        if start_p >= end_p:
          continue

        chap_pdf_name = f"Ch_{chap.number}_{chap.name[:30]}.pdf"
        out_chap_path = os.path.join(DOWNLOAD_DIR, chap_pdf_name)

        new_doc = pymupdf.open()
        new_doc.insert_pdf(doc, from_page=start_p, to_page=end_p - 1)
        new_doc.save(out_chap_path)
        new_doc.close()

        await client.send_document(
            chat_id=chat_id,
            document=out_chap_path,
            caption=(
                f"📖 **Chapter {chap.number}:** {chap.name}\n(Pages:"
                f" {start_p + 1} - {end_p})"
            ),
        )
        if os.path.exists(out_chap_path):
          os.remove(out_chap_path)
  finally:
    shutil.rmtree(temp_preview_dir, ignore_errors=True)
    await gemini_client.close()


# ==========================================
# 📝 SUBROUTINE: MCQ GENERATION
# ==========================================
async def execute_mcq_generation(
    client: Client,
    chat_id: int,
    pdf_path: str,
    file_name: str,
    status_msg: Message,
):
  import pymupdf

  await status_msg.edit_text(f"📝 **Generating MCQs for:** `{file_name}`...")
  gemini_client = await init_gemini_client()
  chat = gemini_client.start_chat(model="gemini-flash-lite")

  out_txt = os.path.join(DOWNLOAD_DIR, f"MCQ_{file_name}.txt")
  lines = []
  curr_counter = 1

  try:
    with pymupdf.open(pdf_path) as doc:
      total_pages = len(doc)
      for p_no in range(total_pages):
        await status_msg.edit_text(
            f"📝 Generating MCQs ({p_no + 1}/{total_pages}) for `{file_name}`..."
        )
        temp_img = os.path.join(DOWNLOAD_DIR, f"temp_mcq_{p_no}.png")
        doc[p_no].get_pixmap(dpi=200).save(temp_img)

        try:
          page_res = await generate_mcqs_for_page(chat, temp_img, p_no + 1)
          for m in page_res.mcqs:
            lines.append(f"{curr_counter}. {m.question} (പേജ് നമ്പർ: {p_no + 1})")
            lines.append(f"A) {m.option_A}")
            lines.append(f"B) {m.option_B}")
            lines.append(f"C) {m.option_C}")
            lines.append(f"D) {m.option_D}")
            lines.append(f"ഉത്തരം: {m.answer_letter}) {m.answer_text}")
            lines.append(f"Sentence : ({m.source_sentence})\n")
            curr_counter += 1
        finally:
          if os.path.exists(temp_img):
            os.remove(temp_img)

    with open(out_txt, "w", encoding="utf-8") as f:
      f.write("\n".join(lines))

    await client.send_document(
        chat_id=chat_id,
        document=out_txt,
        caption=f"📝 **Generated Practice MCQs for:** `{file_name}`",
    )
  finally:
    if os.path.exists(out_txt):
      os.remove(out_txt)
    await gemini_client.close()


# ==========================================
# 📖 SUBROUTINE: TEXT EXTRACTION
# ==========================================
async def execute_text_extraction(
    client: Client,
    chat_id: int,
    pdf_path: str,
    file_name: str,
    status_msg: Message,
):
  import pymupdf

  await status_msg.edit_text(f"📖 **Extracting text from:** `{file_name}`...")
  gemini_client = await init_gemini_client()

  out_txt = os.path.join(DOWNLOAD_DIR, f"EXTRACT_{file_name}.txt")
  all_text = []

  try:
    with pymupdf.open(pdf_path) as doc:
      total = len(doc)
      for p_no in range(total):
        await status_msg.edit_text(
            f"📖 OCR Extraction ({p_no + 1}/{total}) for `{file_name}`..."
        )
        temp_img = os.path.join(DOWNLOAD_DIR, f"temp_ocr_{p_no}.png")
        doc[p_no].get_pixmap(dpi=200).save(temp_img)

        try:
          data = await extract_text_and_tables_webapi(
              gemini_client, temp_img, p_no + 1
          )
          all_text.append(f"--- PAGE {p_no + 1} ---")
          for block in data.blocks:
            if hasattr(block, "text") and block.text:
              all_text.append(block.text)
          all_text.append("\n")
        finally:
          if os.path.exists(temp_img):
            os.remove(temp_img)

    with open(out_txt, "w", encoding="utf-8") as f:
      f.write("\n".join(all_text))

    await client.send_document(
        chat_id=chat_id,
        document=out_txt,
        caption=f"📖 **Extracted Text & Tables for:** `{file_name}`",
    )
  finally:
    if os.path.exists(out_txt):
      os.remove(out_txt)
    await gemini_client.close()


# Compatibility aliases
start_handler = start_cmd
queue_cmd = check_queue_cmd
clear_handler = clear_cmd
done_handler = done_cmd
document_handler = pdf_handler
handle_document = pdf_handler
document_receiver = pdf_handler
callback_query_handler = callback_handler
handle_callback = callback_handler

