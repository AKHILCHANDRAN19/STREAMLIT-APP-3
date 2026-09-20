import os
import re
import pymupdf


def parse_split_pattern(pattern: str, total_pages: int) -> list[int]:
  pages = set()
  parts = [p.strip() for p in pattern.split(",")]
  for part in parts:
    if not part:
      continue
    # 1* = Odd pages (1, 3, 5... -> 0-indexed: 0, 2, 4...)
    if part == "1*":
      pages.update(range(0, total_pages, 2))
    # 2* = Even pages (2, 4, 6... -> 0-indexed: 1, 3, 5...)
    elif part == "2*":
      pages.update(range(1, total_pages, 2))
    # Page range (e.g. 2-5)
    elif "-" in part:
      try:
        s, e = map(int, part.split("-"))
        pages.update(range(s - 1, e))
      except ValueError:
        pass
    # Single page
    else:
      try:
        pages.add(int(part) - 1)
      except ValueError:
        pass
  return sorted([p for p in pages if 0 <= p < total_pages])


def execute_split(input_path: str, pattern: str, output_dir: str) -> list[str]:
  doc = pymupdf.open(input_path)
  total_pages = doc.page_count
  doc.close()

  filename = os.path.basename(input_path)
  is_combine = "/combine" in pattern.lower()
  clean_pattern = re.sub(r"(?i)/combine", "", pattern).strip()
  m = re.match(r"^(\d+)\*$", clean_pattern)

  generated_files = []

  # MODE 1: Combine Mode -> Returns a single unified PDF
  if is_combine:
    pages_to_keep = parse_split_pattern(clean_pattern, total_pages)
    if pages_to_keep:
      out_path = os.path.join(output_dir, f"[Combined_Split] {filename}")
      new_doc = pymupdf.open()
      old_doc = pymupdf.open(input_path)
      for p in pages_to_keep:
        new_doc.insert_pdf(old_doc, from_page=p, to_page=p)
      new_doc.save(out_path)
      new_doc.close()
      old_doc.close()
      generated_files.append(out_path)

  # MODE 2: Chunk Split -> 3* or higher splits into N-page chunks
  elif m and int(m.group(1)) >= 3:
    n = int(m.group(1))
    old_doc = pymupdf.open(input_path)
    for i in range(0, total_pages, n):
      chunk_pages = list(range(i, min(i + n, total_pages)))
      out_path = os.path.join(
          output_dir, f"[Split_{i+1}_to_{chunk_pages[-1]+1}] {filename}"
      )
      new_doc = pymupdf.open()
      for p in chunk_pages:
        new_doc.insert_pdf(old_doc, from_page=p, to_page=p)
      new_doc.save(out_path)
      new_doc.close()
      generated_files.append(out_path)
    old_doc.close()

  # MODE 3: Comma separated parts, 1* (Odd), 2* (Even), or ranges
  else:
    parts = [p.strip() for p in clean_pattern.split(",")]
    for part in parts:
      if not part:
        continue
      safe_part = part.replace("*", "star").replace(" ", "")
      out_path = os.path.join(output_dir, f"[Split_{safe_part}] {filename}")

      pages_to_keep = parse_split_pattern(part, total_pages)
      if pages_to_keep:
        new_doc = pymupdf.open()
        old_doc = pymupdf.open(input_path)
        for p in pages_to_keep:
          new_doc.insert_pdf(old_doc, from_page=p, to_page=p)
        new_doc.save(out_path)
        new_doc.close()
        old_doc.close()
        generated_files.append(out_path)

  return generated_files

