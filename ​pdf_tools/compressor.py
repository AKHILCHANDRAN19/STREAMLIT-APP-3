import pymupdf


def compress_pdf_file(input_path: str, output_path: str) -> str:
  doc = pymupdf.open(input_path)
  doc.save(output_path, garbage=4, deflate=True)
  doc.close()
  return output_path
