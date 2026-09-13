from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_doctype_keyboard() -> InlineKeyboardMarkup:
  """Selection for document structure profile."""
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
