"""Extract text from lecture PDFs under pdf/doc/.

Scratch output goes to pdf/_extracted/ (gitignored). Not a learning artifact.
"""
from __future__ import annotations

import pathlib
import re

import pymupdf

PDF_ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC_DIR = PDF_ROOT / "doc"
OUT_DIR = PDF_ROOT / "_extracted"
OUT_DIR.mkdir(exist_ok=True)


def slug(name: str) -> str:
    stem = pathlib.Path(name).stem
    m = re.match(r"[Ww]eek\s*(\d+)", stem)
    week = m.group(1).zfill(2) if m else "xx"
    return f"week{week}"


def main() -> None:
    if not DOC_DIR.exists():
        raise SystemExit(f"missing lecture dir: {DOC_DIR}")
    for pdf in sorted(DOC_DIR.glob("*.pdf")):
        doc = pymupdf.open(pdf)
        parts = [f"# {pdf.stem}", f"<!-- pages: {doc.page_count} -->", ""]
        for i, page in enumerate(doc):
            text = page.get_text("text").strip()
            parts.append(f"\n## [p{i + 1}]\n")
            parts.append(text if text else "(no extractable text: image-only slide)")
        out = OUT_DIR / f"{slug(pdf.name)}.md"
        out.write_text("\n".join(parts), encoding="utf-8")
        doc.close()
        print(f"{out.name}\t{out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
