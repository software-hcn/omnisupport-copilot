"""Summarize text/image stats for PDFs in pdf/doc/.

Writes inspect_report.json next to this script (gitignored).
"""
from __future__ import annotations

import json
import pathlib

import fitz

PDF_ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC_DIR = PDF_ROOT / "doc"
OUT = pathlib.Path(__file__).resolve().parent / "inspect_report.json"


def main() -> None:
    report = []
    for pdf in sorted(DOC_DIR.glob("*.pdf")):
        doc = fitz.open(pdf)
        pages = []
        for i, page in enumerate(doc):
            text = page.get_text("text").strip()
            pages.append(
                {
                    "page": i + 1,
                    "chars": len(text),
                    "images": len(page.get_images(full=True)),
                    "sample": text[:120].replace("\n", " "),
                }
            )
        total_chars = sum(p["chars"] for p in pages)
        report.append(
            {
                "file": pdf.name,
                "page_count": doc.page_count,
                "total_chars": total_chars,
                "pages_with_text": sum(1 for p in pages if p["chars"] > 20),
                "pages": pages[:5],
            }
        )
        doc.close()

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("written", OUT)


if __name__ == "__main__":
    main()
