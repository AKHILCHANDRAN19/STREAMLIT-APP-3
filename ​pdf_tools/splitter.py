import re
import pymupdf


def parse_split_pattern(pattern: str, total_pages: int) -> list[int]:
  """Parses split patterns: 1* (odd), 2* (even), ranges (2-5), and comma lists."""
  pages = set()
  parts = [p.strip() for p in pattern.split(',')]
  for part in parts:
    if not part:
      continue
    if part == '1*':
      pages.update(range(0, total_pages, 2))
    elif part == '2*':
      pages.update(range(1, total_pages, 2))
    elif '-' in part:
      try:
        start, end = map(int, part.split('-'))
        pages.update(range(start - 1, end))
      except ValueError:
        pass
    else:
      try:
        pages.add(int(part) - 1)
      except ValueError:
        pass
  return sorted([p for p in pages if 0 <= p < total_pages])


def execute_split(input_path: str, pattern: str, output_dir: str) -> list[str]:
  """Splits a PDF by chunks, comma rules, or combines selections with /combine."""
  doc = pymupdf.open(input_path)
  total_pages = doc.page_count
  doc.close()

  is_combine = '/combine' in pattern.lower()
  clean_pattern = re.sub(r'(?i)/combine', '', pattern).strip()
  chunk_match = re.match(r'^(\d+)\*$', clean_pattern)
  generated_files = []

  if is_combine:
    pages_to_keep = parse_split_pattern(clean_pattern, total_pages)
    if pages_to_keep:
      out_path = f"{output_dir}/[Combined_Split].pdf"
      new_doc, old_doc = pymupdf.open(), pymupdf.open(input_path)
      for p in pages_to_keep:
        new_doc.insert_pdf(old_doc, from_page=p, to_page=p)
      new_doc.save(out_path)
      new_doc.close()
      old_doc.close()
      generated_files.append(out_path)

  elif chunk_match and int(chunk_match.group(1)) >= 2:
    step = int(chunk_match.group(1))
    old_doc = pymupdf.open(input_path)
    for i in range(0, total_pages, step):
      chunk_end = min(i + step, total_pages)
      out_path = f"{output_dir}/[Split_{i + 1}_to_{chunk_end}].pdf"
      new_doc = pymupdf.open()
      for p in range(i, chunk_end):
        new_doc.insert_pdf(old_doc, from_page=p, to_page=p)
      new_doc.save(out_path)
      new_doc.close()
      generated_files.append(out_path)
    old_doc.close()

  else:
    parts = [p.strip() for p in clean_pattern.split(',')]
    for part in parts:
      if not part:
        continue
      pages_to_keep = parse_split_pattern(part, total_pages)
      if pages_to_keep:
        safe_part = part.replace('*', 's').replace(' ', '')
        out_path = f"{output_dir}/[Split_{safe_part}].pdf"
        new_doc, old_doc = pymupdf.open(), pymupdf.open(input_path)
        for p in pages_to_keep:
          new_doc.insert_pdf(old_doc, from_page=p, to_page=p)
        new_doc.save(out_path)
        new_doc.close()
        old_doc.close()
        generated_files.append(out_path)

  return generated_files

