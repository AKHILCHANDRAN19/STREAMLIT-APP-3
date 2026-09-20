from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_doctype_keyboard() -> InlineKeyboardMarkup:
  """Selection for document structure profile (Includes new PDF Tools entry)."""
  return InlineKeyboardMarkup([
      [
          InlineKeyboardButton(
              "📌 Pointwise / Notes", callback_data="set_type_pointwise"
          ),
          InlineKeyboardButton(
              "📖 Chapter / Paragraph", callback_data="set_type_chapter"
          ),
      ],
      [
          InlineKeyboardButton(
              "✂️ Smart Chapter Split", callback_data="set_type_split"
          )
      ],
      [
          InlineKeyboardButton(
              "🛠️ Direct PDF Tools", callback_data="open_pdf_tools"
          )
      ],
      [InlineKeyboardButton("🗑️ Clear Queue", callback_data="clear_queue")],
  ])


def get_processing_keyboard() -> InlineKeyboardMarkup:
  """Selection for active processing modes (Gemini WebAPI + Tesseract OCR)."""
  return InlineKeyboardMarkup([
      [
          InlineKeyboardButton(
              "💎 MCQ (Gemini)", callback_data="run_queue_mcq_gem"
          ),
          InlineKeyboardButton(
              "📄 Text (Tesseract OCR)", callback_data="run_queue_text"
          ),
      ],
      [
          InlineKeyboardButton(
              "🌐 Text & Tables (Gemini)", callback_data="run_queue_text_gem"
          ),
          InlineKeyboardButton(
              "💎 Gem + Gem", callback_data="run_queue_both_gem"
          ),
      ],
      [
          InlineKeyboardButton(
              "♻️ Gem + OCR", callback_data="run_queue_both"
          )
      ],
      [InlineKeyboardButton("🗑️ Clear Queue", callback_data="clear_queue")],
  ])


def get_split_keyboard() -> InlineKeyboardMarkup:
  """Confirmation for Smart Chapter Split."""
  return InlineKeyboardMarkup([
      [
          InlineKeyboardButton(
              "✂️ Run Smart Split", callback_data="run_queue_split"
          )
      ],
      [InlineKeyboardButton("🗑️ Clear Queue", callback_data="clear_queue")],
  ])


# ==========================================
# 🆕 PDF TOOLKIT INLINE KEYBOARDS
# ==========================================
def get_pdf_tools_keyboard(
    short_id: str = "", merge_count: int = 0
) -> InlineKeyboardMarkup:
  rows = [
      [
          InlineKeyboardButton(
              "🔢 Page Nums", callback_data=f"tool_pagenum_{short_id}"
          ),
          InlineKeyboardButton(
              "✂️ Pattern Split", callback_data=f"tool_split_{short_id}"
          ),
          InlineKeyboardButton(
              "🗜️ Compress", callback_data=f"tool_compress_{short_id}"
          ),
      ],
      [
          InlineKeyboardButton(
              "🖼️ PDF to Images", callback_data=f"tool_toimg_{short_id}"
          ),
          InlineKeyboardButton(
              "➕ Add to Merge Pool", callback_data=f"tool_addmerge_{short_id}"
          ),
      ],
  ]
  if merge_count >= 1:
    rows.append([
        InlineKeyboardButton(
            f"🔗 Merge All {merge_count} PDFs Now", callback_data="tool_mergenow"
        ),
        InlineKeyboardButton(
            "🗑️ Clear Merge Pool", callback_data="tool_clearmerge"
        ),
    ])
  rows.append([
      InlineKeyboardButton(
          "🔙 Back to Queue Menu", callback_data="back_to_queue"
      )
  ])
  return InlineKeyboardMarkup(rows)


def get_image_tools_keyboard(count: int = 0) -> InlineKeyboardMarkup:
  return InlineKeyboardMarkup([
      [
          InlineKeyboardButton(
              f"🖼️ Convert {count} Images to PDF",
              callback_data="tool_img2pdf_convert",
          )
      ],
      [
          InlineKeyboardButton(
              "🗑️ Clear Image Pool", callback_data="tool_img2pdf_clear"
          )
      ],
  ])
