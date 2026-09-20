import pymupdf


def stamp_page_numbers(
    input_path: str,
    output_path: str,
    margin_right: int = 40,
    margin_bottom: int = 30,
) -> str:
  """Inserts sequential page numbers at the bottom-right corner of each page."""
  doc = pymupdf.open(input_path)
  for index, page in enumerate(doc):
    rect = page.rect
    point = pymupdf.Point(
        rect.width - margin_right, rect.height - margin_bottom
    )
    page.insert_text(point, str(index + 1), fontsize=12, color=(0, 0, 0))
  doc.save(output_path)
  doc.close()
  return output_path

