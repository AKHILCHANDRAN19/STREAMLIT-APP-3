import os
import re
import uuid
import pymupdf


def get_pdf_page_count(pdf_path: str) -> int:
  """Returns total pages in the PDF document."""
  ext = pdf_path.lower().split(".")[-1]
  if ext in ["png", "jpg", "jpeg", "txt", "json"]:
    return 1
  try:
    with pymupdf.open(pdf_path) as doc:
      return len(doc)
  except Exception:
    return 0


def render_page_image(
    pdf_path: str, page_index: int, output_img_path: str, dpi: int = 300
) -> str:
  """Renders a single PDF page to a PNG at the requested DPI."""
  with pymupdf.open(pdf_path) as doc:
    if 0 <= page_index < len(doc):
      page = doc.load_page(page_index)
      pix = page.get_pixmap(dpi=dpi)
      pix.save(output_img_path)
      return output_img_path
  raise IndexError(f"Page index {page_index} out of range for {pdf_path}")


def render_preview_pages(
    pdf_path: str, temp_dir: str, max_pages: int = 15, dpi: int = 150
) -> list[str]:
  """Renders the first N preview pages at 150 DPI for index/TOC discovery."""
  image_paths = []
  with pymupdf.open(pdf_path) as doc:
    limit = min(max_pages, len(doc))
    for i in range(limit):
      page = doc[i]
      pix = page.get_pixmap(dpi=dpi)
      img_path = os.path.join(
          temp_dir, f"temp_preview_{uuid.uuid4().hex[:6]}_{i}.jpg"
      )
      pix.save(img_path)
      image_paths.append(img_path)
  return image_paths


def split_pdf_by_verified_chapters(
    pdf_path: str, verified_chapters: list[dict], output_dir: str
) -> list[str]:
  """Slices the source PDF into individual chapter PDFs based on verified start pages."""
  split_files = []
  with pymupdf.open(pdf_path) as doc:
    total_pages = len(doc)
    for i, chap in enumerate(verified_chapters):
      chap_num = chap["chapter_number"]
      chap_name = chap["chapter_name"]
      start_idx = chap["start_index"]

      if i < len(verified_chapters) - 1:
        end_idx = verified_chapters[i + 1]["start_index"] - 1
      else:
        end_idx = total_pages - 1

      if start_idx > end_idx or start_idx >= total_pages:
        continue

      new_doc = pymupdf.open()
      new_doc.insert_pdf(doc, from_page=start_idx, to_page=end_idx)

      safe_name = re.sub(r'[\\/*?:"<>|]', "", chap_name).strip()
      out_filename = os.path.join(
          output_dir, f"Chapter_{chap_num}_{safe_name}.pdf"
      )
      new_doc.save(out_filename)
      new_doc.close()
      split_files.append(out_filename)

  return split_files

