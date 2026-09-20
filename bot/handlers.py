import asyncio
import os
import uuid
import zipfile
from bot.keyboards import (
    get_doctype_keyboard,
    get_image_tools_keyboard,
    get_pdf_tools_keyboard,
    get_processing_keyboard,
    get_split_keyboard,
)
from bot.pipeline import run_queue_pipeline
from bot.queue_manager import USER_QUEUE
from config import DOWNLOAD_DIR, OWNER_IDS
from pdf_tools import (
    compile_images_into_pdf,
    compress_pdf_file,
    execute_split,
    extract_pdf_pages_as_images,
    merge_pdf_list,
    parse_split_pattern,
    stamp_page_numbers,
)
import pymupdf
from pyrogram.types import CallbackQuery, Message
from utils.telemetry import GLOBAL_STATE

WELCOME_TEXT = (
    "🎯 **Welcome to the GenAI & PDF Toolkit Bot** 🎯\n\n"
    "Powered strictly by modern WebAPI sessions, PyMuPDF, and WeasyPrint.\n\n"
    "🤖 **Available Commands:**\n"
    "🔹 `/start` - View guide & reset state\n"
    "🔹 `/queue` - Check current queued files\n"
    "🔹 `/done` - Finalize queue & select action\n"
    "🔹 `/clear` - Empty all queues and tool pools\n\n"
    "📥 **How to Use:**\n"
    "1️⃣ Send one or more `.pdf`, images, or `.txt` files.\n"
    "2️⃣ Select Pointwise, Chapter, or Smart Chapter Split for AI processing.\n"
    "3️⃣ Or click **🛠️ Direct PDF Tools** for Page Nums, Compress, Split, Merge, or Image Extraction!"
)

# Tool state management
user_tool_states: dict[int, dict] = {}
pdf_merge_pools: dict[int, list[dict]] = {}
img2pdf_pools: dict[int, list[str]] = {}
latest_user_pdf: dict[int, dict] = {}


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
    text += "\n📑 **Structure:** `✂️ Smart Split`\n\n👉 Click below to proceed:"
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
  pdf_merge_pools[user_id] = []
  img2pdf_pools[user_id] = []
  if user_id in user_tool_states:
    del user_tool_states[user_id]

  await message.reply_text("🗑️ **All Queues & Tool Pools Cleared.**")


async def handle_document(client, message: Message):
  user_id = message.from_user.id if message.from_user else 0
  if not is_authorized(user_id):
    return

  # Photo handling for Images-to-PDF tool
  if message.photo:
    if user_id not in img2pdf_pools:
      img2pdf_pools[user_id] = []
    img2pdf_pools[user_id].append(message.photo.file_id)
    count = len(img2pdf_pools[user_id])
    return await message.reply_text(
        f"🖼️ Photo added to Image Pool! Total: `{count}`",
        reply_markup=get_image_tools_keyboard(count),
    )

  file_name = "unknown.pdf"
  if message.document:
    file_name = message.document.file_name or f"doc_{uuid.uuid4().hex[:6]}.pdf"

  # Direct image document handling
  if file_name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
    if user_id not in img2pdf_pools:
      img2pdf_pools[user_id] = []
    img2pdf_pools[user_id].append(message.document.file_id)
    count = len(img2pdf_pools[user_id])
    return await message.reply_text(
        f"🖼️ Image document added to Image Pool! Total: `{count}`",
        reply_markup=get_image_tools_keyboard(count),
    )

  if USER_QUEUE.is_processing(user_id):
    return await message.reply_text(
        "⚠️ Current batch is still processing. Please wait for completion."
    )

  status_msg = await message.reply_text("📥 **Downloading to local queue...**")
  dest_path = os.path.join(DOWNLOAD_DIR, f"{uuid.uuid4().hex[:6]}_{file_name}")
  await message.download(file_name=dest_path)

  # Save into AI queue
  USER_QUEUE.add_file(user_id, dest_path, file_name, message.id)

  # Track as latest PDF for Direct Tools
  short_id = uuid.uuid4().hex[:8]
  latest_user_pdf[user_id] = {
      "path": dest_path,
      "name": file_name,
      "short_id": short_id,
      "file_id": message.document.file_id,
  }

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
        base_text + "👉 Select document structure or open tools:",
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


# ==========================================
# 🔘 CALLBACK QUERY ROUTER (OLD + NEW)
# ==========================================
async def queue_callbacks(client, callback_query: CallbackQuery):
  user_id = callback_query.from_user.id
  if not is_authorized(user_id):
    return await callback_query.answer("⚠️ Unauthorized.", show_alert=True)

  data = callback_query.data

  # --- 1. EXISTING QUEUE CALLBACKS ---
  if data == "clear_queue":
    USER_QUEUE.clear_queue(user_id)
    await callback_query.edit_message_text("🗑️ **Queue cleared successfully.**")
    return await callback_query.answer("Queue cleared")

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

  if data.startswith("run_queue_"):
    if not USER_QUEUE.get_files(user_id):
      return await callback_query.answer(
          "❌ Queue is empty or expired.", show_alert=True
      )
    if USER_QUEUE.is_processing(user_id):
      return await callback_query.answer(
          "⚠️ Batch currently active.", show_alert=True
      )

    mode = data.replace("run_queue_", "")
    USER_QUEUE.set_processing(user_id, True)
    await callback_query.answer("Processing started!")
    asyncio.create_task(
        run_queue_pipeline(client, callback_query.message, user_id, mode)
    )
    return

  # --- 2. NEW DIRECT PDF TOOLS CALLBACKS ---
  if data == "open_pdf_tools":
    fdata = latest_user_pdf.get(user_id)
    if not fdata:
      return await callback_query.answer(
          "No active PDF found. Send a PDF first!", show_alert=True
      )
    merge_count = len(pdf_merge_pools.get(user_id, []))
    await callback_query.edit_message_text(
        f"🛠️ **Direct PDF Tools** for `{fdata['name']}`:\nSelect a tool:",
        reply_markup=get_pdf_tools_keyboard(fdata["short_id"], merge_count),
    )
    return

  if data == "back_to_queue":
    q_len = len(USER_QUEUE.get_files(user_id))
    await callback_query.edit_message_text(
        f"📊 **Queue Menu ({q_len} files)**\nSelect document structure:",
        reply_markup=get_doctype_keyboard(),
    )
    return

  if data.startswith("tool_pagenum_"):
    fdata = latest_user_pdf.get(user_id)
    if not fdata or not os.path.exists(fdata["path"]):
      return await callback_query.answer("File session expired.", show_alert=True)
    await callback_query.message.edit_text("⏳ Stamping page numbers...")
    out_p = os.path.join(DOWNLOAD_DIR, f"[Numbered]_{fdata['name']}")
    await asyncio.to_thread(stamp_page_numbers, fdata["path"], out_p)
    await client.send_document(
        user_id, out_p, caption=f"🔢 Numbered: `{fdata['name']}`"
    )
    if os.path.exists(out_p):
      os.remove(out_p)
    await callback_query.message.delete()
    return

  if data.startswith("tool_compress_"):
    fdata = latest_user_pdf.get(user_id)
    if not fdata or not os.path.exists(fdata["path"]):
      return await callback_query.answer("File session expired.", show_alert=True)
    await callback_query.message.edit_text("⏳ Compressing PDF...")
    out_p = os.path.join(DOWNLOAD_DIR, f"[Compressed]_{fdata['name']}")
    await asyncio.to_thread(compress_pdf_file, fdata["path"], out_p)
    await client.send_document(
        user_id, out_p, caption=f"🗜️ Compressed: `{fdata['name']}`"
    )
    if os.path.exists(out_p):
      os.remove(out_p)
    await callback_query.message.delete()
    return

  if data.startswith("tool_addmerge_"):
    fdata = latest_user_pdf.get(user_id)
    if not fdata:
      return await callback_query.answer("File session expired.", show_alert=True)
    if user_id not in pdf_merge_pools:
      pdf_merge_pools[user_id] = []
    pdf_merge_pools[user_id].append(fdata)
    count = len(pdf_merge_pools[user_id])
    await callback_query.message.edit_text(
        f"✅ Added `{fdata['name']}` to merge queue. Total in pool:"
        f" `{count}`\nSend another PDF or click Merge All Now.",
        reply_markup=get_pdf_tools_keyboard(fdata["short_id"], count),
    )
    return

  if data == "tool_mergenow":
    pool = pdf_merge_pools.get(user_id, [])
    if len(pool) < 2:
      return await callback_query.answer(
          "You need at least 2 PDFs in the pool to merge!", show_alert=True
      )
    await callback_query.message.edit_text("⏳ Merging queued documents...")
    files_to_merge = [f["path"] for f in pool if os.path.exists(f["path"])]
    out_p = os.path.join(
        DOWNLOAD_DIR, f"Merged_Document_{uuid.uuid4().hex[:6]}.pdf"
    )
    await asyncio.to_thread(merge_pdf_list, files_to_merge, out_p)
    await client.send_document(
        user_id, out_p, caption=f"🔗 Merged {len(files_to_merge)} PDFs."
    )
    if os.path.exists(out_p):
      os.remove(out_p)
    pdf_merge_pools[user_id] = []
    await callback_query.message.delete()
    return

  if data == "tool_clearmerge":
    pdf_merge_pools[user_id] = []
    await callback_query.answer("Merge pool cleared!", show_alert=True)
    await callback_query.message.edit_text("🗑️ PDF Merge Pool cleared.")
    return

  if data.startswith("tool_split_"):
    fdata = latest_user_pdf.get(user_id)
    if not fdata:
      return await callback_query.answer("File session expired.", show_alert=True)
    user_tool_states[user_id] = {"action": "split"}
    await callback_query.message.edit_text(
        f"✂️ **PDF Splitter: `{fdata['name']}`**\n\n"
        "Send the page pattern you want to split:\n"
        "• `1*` (Odd pages: 1, 3, 5...)\n"
        "• `2*` (Even pages: 2, 4, 6...)\n"
        "• `3*` or `4*` (Splits into chunks of 3 or 4 pages)\n"
        "• `2-5` (Extract pages 2 to 5)\n"
        "• `1, 10, 17` (Creates 3 separate PDFs)\n"
        "• `1-5, 8-10` (Creates 2 separate PDFs)\n"
        "• `1-5, 8-10 /combine` (Combines specified pages into ONE PDF)\n\n"
        "Reply with your pattern text:"
    )
    return

  if data.startswith("tool_toimg_"):
    fdata = latest_user_pdf.get(user_id)
    if not fdata:
      return await callback_query.answer("File session expired.", show_alert=True)
    user_tool_states[user_id] = {"action": "toimg"}
    await callback_query.message.edit_text(
        f"🖼️ **PDF to Images: `{fdata['name']}`**\n\n"
        "Send your conversion request:\n"
        "• Type `all` (Converts all pages to a ZIP)\n"
        "• Or send a pattern: `1*` (Odd), `2*` (Even), `2-5`, `1, 10, 17`\n\n"
        "Reply with your pattern text:"
    )
    return

  if data == "tool_img2pdf_convert":
    images = img2pdf_pools.get(user_id, [])
    if not images:
      return await callback_query.answer(
          "No images found in pool!", show_alert=True
      )
    await callback_query.message.edit_text(
        "⏳ Converting images to unified PDF..."
    )
    downloaded_imgs = []
    for idx, fid in enumerate(images):
      tmp_p = os.path.join(DOWNLOAD_DIR, f"temp_img_{user_id}_{idx}.png")
      p = await client.download_media(fid, file_name=tmp_p)
      downloaded_imgs.append(p)

    out_p = os.path.join(DOWNLOAD_DIR, f"Images_Output_{uuid.uuid4().hex[:6]}.pdf")
    await asyncio.to_thread(compile_images_into_pdf, downloaded_imgs, out_p)
    await client.send_document(
        user_id,
        out_p,
        caption=f"✅ Converted {len(downloaded_imgs)} images into PDF.",
    )

    for p in downloaded_imgs + [out_p]:
      if os.path.exists(p):
        os.remove(p)
    img2pdf_pools[user_id] = []
    await callback_query.message.delete()
    return

  if data == "tool_img2pdf_clear":
    img2pdf_pools[user_id] = []
    await callback_query.answer("Image pool cleared!", show_alert=True)
    await callback_query.message.edit_text("🗑️ Image Pool cleared.")
    return


# ==========================================
# 💬 TEXT PATTERN HANDLER FOR PDF TOOLS
# ==========================================
async def handle_pattern_text(client, message: Message):
  user_id = message.from_user.id if message.from_user else 0
  if user_id not in user_tool_states:
    return

  state = user_tool_states.pop(user_id)
  action = state["action"]
  pattern = message.text.strip()
  fdata = latest_user_pdf.get(user_id)

  if not fdata or not os.path.exists(fdata["path"]):
    return await message.reply_text(
        "❌ PDF file session expired. Please upload the PDF again."
    )

  status = await message.reply_text("⏳ Processing with PyMuPDF...")
  try:
    if action == "split":
      generated = await asyncio.to_thread(
          execute_split, fdata["path"], pattern, DOWNLOAD_DIR
      )
      if not generated:
        await status.edit_text("❌ No pages matched the pattern.")
      else:
        for f in generated:
          await client.send_document(user_id, f)
          if os.path.exists(f):
            os.remove(f)
        await status.delete()

    elif action == "toimg":
      if pattern.lower() == "all":
        images = await asyncio.to_thread(
            extract_pdf_pages_as_images, fdata["path"], None, DOWNLOAD_DIR
        )
        zip_p = os.path.join(
            DOWNLOAD_DIR, f"Images_{os.path.splitext(fdata['name'])[0]}.zip"
        )
        with zipfile.ZipFile(zip_p, "w", zipfile.ZIP_DEFLATED) as zipf:
          for img in images:
            zipf.write(img, os.path.basename(img))
            if os.path.exists(img):
              os.remove(img)
        await client.send_document(
            user_id,
            zip_p,
            caption=f"✅ All Images for `{fdata['name']}` (ZIP Archive)",
        )
        if os.path.exists(zip_p):
          os.remove(zip_p)
        await status.delete()
      else:
        doc = pymupdf.open(fdata["path"])
        total = doc.page_count
        doc.close()
        targets = parse_split_pattern(pattern, total)
        images = await asyncio.to_thread(
            extract_pdf_pages_as_images, fdata["path"], targets, DOWNLOAD_DIR
        )
        if not images:
          await status.edit_text("❌ No pages matched the pattern.")
        else:
          for img in images:
            await client.send_photo(user_id, img)
            if os.path.exists(img):
              os.remove(img)
          await status.delete()
  except Exception as e:
    await status.edit_text(f"❌ Error: {e}")


# Explicit compatibility aliases for client.py
start_handler = start_cmd
queue_cmd = check_queue_cmd
clear_handler = clear_cmd
done_handler = done_cmd
pdf_handler = handle_document
document_receiver = handle_document
callback_handler = queue_callbacks
handle_callback = queue_callbacks

