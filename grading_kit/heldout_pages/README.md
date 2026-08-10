Put page-IMAGES here that you set aside and NEVER train or tune OCR on.
A grader authors fresh questions from these pages and checks answers against
../labels.jsonl. Seed a few pages in A1; add more (each with a transcription
in labels.jsonl) as your OCR matures in A2.

## Our workflow (Group 14 — target ~30 pages, ~10 per member)

1. After `bash scripts/get_data.sh`, pick pages spanning the difficulty range:
   clean prose, list-like remedy pages (Bengali potency numerals), foxed/faded
   pages, and footnote-heavy pages — so OCR CER is measured across the real spread.
2. Copy each chosen page-image here, named by our id convention: `<book>_p<NNN>.jp2`
   (e.g. `bk1_p052.jp2`, `bk2_p170.jp2`). Same ids used in ../labels.jsonl and the index.
3. Hand-transcribe each page EXACTLY (Unicode NFC, keep Bengali numerals ০–৯, keep
   transliterated remedy names as printed) into one JSONL line in ../labels.jsonl:
   `{"page_id": "bk1_p052", "text": "<exact transcription>"}`
4. These pages are the OCR oracle for A2 Section 5 (25 pts) — do NOT OCR-train or tune on them.

Split reminder: held-out pages come from bk1 (the test book) plus a few from other
books to cover script variety; keep the by-document split intact.
