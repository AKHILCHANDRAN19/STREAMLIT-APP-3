import pymupdf


def extract_pdf_pages_as_images(
    input_path: str,
    page_indices: list[int] | None,
    output_dir: str,
    dpi: int = 150,
) -> list[str]:
  """Renders specified PDF pages into standalone PNG images."""
  doc = pymupdf.open(input_path)
  total_pages = doc.page_count
  targets = page_indices if page_indices is not None else list(range(total_pages))
  saved_images = []

  for p in targets:
    if 0 <= p < total_pages:
      page = doc.load_page(p)
      pix = page.get_pixmap(dpi=dpi)
      img_path = f"{output_dir}/page_{p + 1}.png"
      pix.save(img_path)
      saved_images.append(img_path)

  doc.close()
  return saved_images


def compile_images_into_pdf(image_paths: list[str], output_path: str) -> str:
  """Converts a sequence of images into a single unified PDF."""
  doc = pymupdf.open()
  for img in image_paths:
    with pymupdf.open(img) as img_doc:
      pdf_bytes = img_doc.convert_to_pdf()
      with pymupdf.open("pdf", pdf_bytes) as img_pdf:
        doc.insert_pdf(img_pdf)
  doc.save(output_path)
  doc.close()
  return output_path

