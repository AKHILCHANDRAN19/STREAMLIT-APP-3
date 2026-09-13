import io
import logging
import os
import re
from PIL import Image
import pymupdf
import pytesseract

logger = logging.getLogger("OCR_Service")


def clean_ocr_text(text: str) -> str:
  """Sanitizes raw Tesseract OCR output and normalizes bullet points."""
  text = re.sub(r"(?i)(©\s*entri|e\s*entri|thank\s*you)", "", text)
  text = re.sub(r"^[ \t]*```", "", text)  # Fixed unclosed subpattern
  text = re.sub(
      r"^[ \t]*(൭൫|൭|©|e|@|\*|-|~)[ \t]*", "• ", text, flags=re.MULTILINE
  )
  lines = [line.strip() for line in text.split("\n") if line.strip()]
  text = "\n".join(lines)
  text = re.sub(r"\n(•|\d+\.)", r"\n\n\1", text)
  text = re.sub(r"\n{3,}", "\n\n", text)
  return text.strip()


def extract_text_with_tesseract(file_path: str) -> str:
  """Extracts Malayalam and English text across images, text, and PDF documents."""
  extracted_text = ""
  ext = file_path.lower().split(".")[-1]

  if ext in ["txt", "json"]:
    with open(file_path, "r", encoding="utf-8") as f:
      extracted_text = f.read()
  elif ext in ["png", "jpg", "jpeg"]:
    try:
      img = Image.open(file_path)
      text = pytesseract.image_to_string(img, lang="eng+mal")
      extracted_text += text + "\n"
    except Exception as e:
      logger.error(f"OCR error on image: {e}")
  else:
    try:
      with pymupdf.open(file_path) as doc:
        for page_num in range(len(doc)):
          page = doc.load_page(page_num)
          pix = page.get_pixmap(dpi=150)
          img_bytes = pix.tobytes("png")
          img = Image.open(io.BytesIO(img_bytes))
          text = pytesseract.image_to_string(img, lang="eng+mal")
          extracted_text += f"--- Page {page_num + 1} ---\n{text}\n\n"
    except Exception as e:
      logger.error(f"OCR error on PDF: {e}")

  return clean_ocr_text(extracted_text)
