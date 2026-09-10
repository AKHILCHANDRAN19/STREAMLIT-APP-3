import asyncio
import json
import logging
import os
import pathlib
import uuid
from bot.queue_manager import USER_QUEUE
from config import DELAY_BETWEEN_PAGES, DOWNLOAD_DIR, MAX_PAGES_PER_RUN, TARGET_CHANNEL_ID
from services.export_service import compile_pdf_with_weasyprint, save_bot_txt
from services.gemini_service import (
    analyze_document_title,
    extract_table_of_contents,
    extract_text_and_tables_webapi,
    generate_mcqs_for_page,
    init_gemini_client,
    verify_chapter_page,
)
from services.pdf_service import (
    get_pdf_page_count,
    render_page_image,
    render_preview_pages,
    split_pdf_by_verified_chapters,
)

logger = logging.getLogger("Pipeline_Coordinator")


async def run_queue_pipeline(client, status_msg, user_id: int, mode: str):
  """Executes queued items sequentially and dispatches deliverables."""
  queue_files = list(USER_QUEUE.get_files(user_id))
  total_files = len(queue_files)
  doc_type = USER_QUEUE.get_doc_type(user_id) or "pointwise"

  gem_client = None
  try:
    await status_msg.edit_text("🏁 **Connecting Gemini WebAPI session...**")
    gem_client = await init_gemini_client()
    await status_msg.edit_text(
        f"🏁 **Starting batch of {total_files} file(s) in `{mode.upper()}`"
        " mode...**"
    )
    await asyncio.sleep(1)

    for idx, f_info in enumerate(queue_files, 1):
      file_path = f_info["path"]
      original_name = f_info["name"]

      item_status = await client.send_message(
          user_id,
          f"🎬 **[{idx}/{total_files}] Processing:** `{original_name}`\n\n⏳"
          " Initializing document...",
      )

      # ----------------------------------------------------
      # ✂️ SMART CHAPTER SPLIT PIPELINE
      # ----------------------------------------------------
      if mode == "split":
        await item_status.edit_text(
            f"🎬 **[{idx}/{total_files}]** `{original_name}`\n\n🔍 **Step 1:**"
            " Analyzing Table of Contents..."
        )
        preview_images = render_preview_pages(
            file_path, DOWNLOAD_DIR, max_pages=15
        )
        split_chat = gem_client.start_chat()

        try:
          analysis = await extract_table_of_contents(split_chat, preview_images)
        finally:
          for p in preview_images:
            if os.path.exists(p):
              os.remove(p)

        if not analysis.found_index or not analysis.chapters:
          await item_status.edit_text(
              f"❌ Could not find Table of Contents in `{original_name}`."
          )
          continue

        await item_status.edit_text(
            f"🎬 **[{idx}/{total_files}]** `{original_name}`\n\n🔍 **Step 2:**"
            f" Visually verifying {len(analysis.chapters)} chapter starts..."
        )
        doc_page_count = get_pdf_page_count(file_path)
        current_offset = analysis.offset
        verified = []

        for c_idx, chap in enumerate(analysis.chapters):
          pred_idx = chap.printed_page_number + current_offset
          actual_idx = pred_idx
          search_window = [0, 1, -1, 2, -2, 3, -3]

          for shift in search_window:
            cand_idx = pred_idx + shift
            if 0 <= cand_idx < doc_page_count:
              temp_v = os.path.join(
                  DOWNLOAD_DIR, f"verify_{uuid.uuid4().hex[:6]}.jpg"
              )
              render_page_image(file_path, cand_idx, temp_v, dpi=150)
              try:
                if await verify_chapter_page(
                    split_chat, temp_v, chap.chapter_number, chap.chapter_name
                ):
                  actual_idx = cand_idx
                  break
              finally:
                if os.path.exists(temp_v):
                  os.remove(temp_v)

          if c_idx == 0 and actual_idx != pred_idx:
            current_offset = actual_idx - chap.printed_page_number

          verified.append({
              "chapter_number": chap.chapter_number,
              "chapter_name": chap.chapter_name,
              "start_index": actual_idx,
          })

        await item_status.edit_text(
            f"🎬 **[{idx}/{total_files}]** `{original_name}`\n\n✂️ **Step 3:**"
            " Slicing PDF chapters..."
        )
        split_files = split_pdf_by_verified_chapters(
            file_path, verified, DOWNLOAD_DIR
        )

        for s_file in split_files:
          await client.send_document(user_id, s_file)
          try:
            await client.send_document(TARGET_CHANNEL_ID, s_file)
          except Exception:
            pass
          if os.path.exists(s_file):
            os.remove(s_file)

        await item_status.delete()
        continue

      # ----------------------------------------------------
      # 📄 MCQ & TEXT EXTRACTION PIPELINES
      # ----------------------------------------------------
      total_pages = get_pdf_page_count(file_path)
      if total_pages == 0:
        await item_status.edit_text(
            f"❌ Unable to read `{original_name}`. Skipping."
        )
        continue

      total_pages = min(total_pages, MAX_PAGES_PER_RUN)
      doc_title = f"Document_{uuid.uuid4().hex[:6]}"

      # Render Page 1 to determine title
      p1_img = os.path.join(DOWNLOAD_DIR, f"p1_{uuid.uuid4().hex[:6]}.png")
      render_page_image(file_path, 0, p1_img, dpi=150)
      active_chat = gem_client.start_chat()
      doc_title = await analyze_document_title(active_chat, p1_img)
      if os.path.exists(p1_img):
        os.remove(p1_img)

      out_txt_path = os.path.join(DOWNLOAD_DIR, f"{doc_title}.txt")
      out_pdf_path = os.path.join(DOWNLOAD_DIR, f"{doc_title}.pdf")
      out_html_path = os.path.join(DOWNLOAD_DIR, f"{doc_title}.html")
      gem_text_path = os.path.join(DOWNLOAD_DIR, f"{doc_title}_Extracted.txt")

      all_mcqs = []

      for page_num in range(1, total_pages + 1):
        await item_status.edit_text(
            f"🎬 **[{idx}/{total_files}] Processing:** `{original_name}`\n\n⚙️"
            f" **Working on Page {page_num} of {total_pages}**\n📊 MCQs so"
            f" far: `{len(all_mcqs)}`"
        )

        curr_img = os.path.join(
            DOWNLOAD_DIR, f"run_p_{page_num}_{uuid.uuid4().hex[:4]}.png"
        )
        render_page_image(file_path, page_num - 1, curr_img, dpi=300)

        try:
          # Mode: Text & Tables Extraction
          if mode in ["text_gem", "both_gem"]:
            page_blocks = await extract_text_and_tables_webapi(
                gem_client, curr_img, page_num
            )
            with open(gem_text_path, "a", encoding="utf-8") as f:
              f.write(f"\n=== PAGE {page_num} ===\n\n")
              for b in page_blocks.blocks:
                if b.block_type == "text" and b.text_content:
                  f.write(f"{b.text_content.strip()}\n\n")
                elif b.block_type == "table" and b.table_content:
                  f.write("--- TABLE ---\n")
                  hdrs = b.table_content.headers
                  for row in b.table_content.rows:
                    for c_idx, cell in enumerate(row.cells):
                      h_label = (
                          hdrs[c_idx]
                          if c_idx < len(hdrs)
                          else f"Col {c_idx+1}"
                      )
                      f.write(f"• {h_label}: {cell}\n")
                    f.write("------------------\n")

          # Mode: MCQ Generation
          if mode in ["mcq_gem", "both_gem"]:
            mcq_res = await generate_mcqs_for_page(
                active_chat, curr_img, page_num, doc_type=doc_type
            )
            all_mcqs.extend([m.model_dump() for m in mcq_res.mcqs])
            save_bot_txt(all_mcqs, out_txt_path)

        finally:
          if os.path.exists(curr_img):
            os.remove(curr_img)

        await asyncio.sleep(DELAY_BETWEEN_PAGES)

      # ----------------------------------------------------
      # 📤 ARTIFACT DISPATCH & ARCHIVE SYNC
      # ----------------------------------------------------
      await item_status.edit_text(
          f"🎬 **[{idx}/{total_files}] Compiling deliverables...**"
      )

      # Deliver Text & Tables File
      if (
          mode in ["text_gem", "both_gem"]
          and os.path.exists(gem_text_path)
          and os.path.getsize(gem_text_path) > 0
      ):
        caption = (
            f"🌐 **Extracted Text & Tables**\n📁 File: `{original_name}`\n👤"
            f" User: `{user_id}`"
        )
        await client.send_document(user_id, gem_text_path, caption=caption)
        try:
          await client.send_document(
              TARGET_CHANNEL_ID, gem_text_path, caption=caption
          )
        except Exception:
          pass

      # Deliver MCQ Output Files
      if mode in ["mcq_gem", "both_gem"] and all_mcqs:
        compile_pdf_with_weasyprint(
            all_mcqs, doc_title, out_pdf_path, out_html_path
        )
        caption = (
            f"🎬 **MCQ Practice Drill [{idx}/{total_files}]**\n💾 Total"
            f" Questions: `{len(all_mcqs)}`\n👤 User: `{user_id}`"
        )

        if os.path.exists(out_txt_path):
          await client.send_document(user_id, out_txt_path, caption=caption)
          try:
            await client.send_document(
                TARGET_CHANNEL_ID, out_txt_path, caption=caption
            )
          except Exception:
            pass

        if os.path.exists(out_pdf_path):
          await client.send_document(
              user_id,
              out_pdf_path,
              caption="🎨 **Formatted Custom Font PDF (+10pt).**",
          )
          try:
            await client.send_document(
                TARGET_CHANNEL_ID,
                out_pdf_path,
                caption=f"🎨 Formatted PDF for User {user_id}",
            )
          except Exception:
            pass
        elif os.path.exists(out_html_path):
          await client.send_document(
              user_id,
              out_html_path,
              caption="🌐 **HTML Fallback (PDF compile skipped).**",
          )

      # Cleanup finished files
      for tmp in [
          file_path,
          out_txt_path,
          out_pdf_path,
          out_html_path,
          gem_text_path,
      ]:
        if os.path.exists(tmp):
          try:
            os.remove(tmp)
          except Exception:
            pass

      await item_status.delete()

    await status_msg.edit_text("🎉 **Batch Processing Complete!**")

  except Exception as err:
    logger.error(f"Pipeline failure: {err}")
    await status_msg.edit_text(f"❌ **Pipeline encountered an error:** {err}")

  finally:
    USER_QUEUE.clear_queue(user_id)
    USER_QUEUE.set_processing(user_id, False)
    if gem_client:
      try:
        await gem_client.close()
      except Exception:
        pass

