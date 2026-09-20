import os
import zipfile
from pdf_tools.splitter import parse_split_pattern
import pymupdf


def extract_pdf_to_images(
    input_path: str, pattern: str, output_dir: str, dpi: int = 150
) -> str | list[str]:
  doc = pymupdf.open(input_path)
  total_pages = doc.page_count
  base_name = os.path.splitext(os.path.basename(input_path))[0]

  # If 'all': pack all rendered pages into a single ZIP file
  if pattern.strip().lower() == "all":
    zip_path = os.path.join(output_dir, f"[Images] {base_name}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
      for p in range(total_pages):
        page = doc.load_page(p)
        pix = page.get_pixmap(dpi=dpi)
        img_path = os.path.join(output_dir, f"page_{p + 1}.png")
        pix.save(img_path)
        zipf.write(img_path, os.path.basename(img_path))
        if os.path.exists(img_path):
          os.remove(img_path)
    doc.close()
    return zip_path

  # Otherwise: extract only pages matching the pattern (1*, 2*, 1-5, etc.)
  pages_to_convert = parse_split_pattern(pattern, total_pages)
  image_paths = []
  for p in pages_to_convert:
    page = doc.load_page(p)
    pix = page.get_pixmap(dpi=dpi)
    img_path = os.path.join(output_dir, f"page_{p + 1}.png")
    pix.save(img_path)
    image_paths.append(img_path)

  doc.close()
  return image_paths


def compile_images_into_pdf(image_paths: list[str], output_path: str) -> str:
  doc = pymupdf.open()
  for img in image_paths:
    with pymupdf.open(img) as img_doc:
      pdf_bytes = img_doc.convert_to_pdf()
      with pymupdf.open("pdf", pdf_bytes) as img_pdf:
        doc.insert_pdf(img_pdf)
  doc.save(output_path)
  doc.close()
  return output_path
