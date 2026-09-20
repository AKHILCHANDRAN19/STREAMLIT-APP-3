import pymupdf


def merge_pdf_list(file_paths: list[str], output_path: str) -> str:
  merged_doc = pymupdf.open()
  for path in file_paths:
    with pymupdf.open(path) as doc:
      merged_doc.insert_pdf(doc)
  merged_doc.save(output_path)
  merged_doc.close()
  return output_path
