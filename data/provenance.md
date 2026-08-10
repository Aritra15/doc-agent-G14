# Corpus provenance — BanglaHomeoRAG (Group 14)

Scanned public-domain Bengali homeopathy manuals from the **Digital Library of India**
collection on the Internet Archive. These are **scanned page-images** (JP2/PDF), not pre-typed
text — reading the image is the point of the project. Recreate the corpus with
`bash scripts/get_data.sh` (raw scans are gitignored, never committed).

## Books

| ID | Book | Year | Author | Split | Archive.org identifier |
|----|------|------|--------|-------|------------------------|
| bk1 | Homeopathic Paribarik Chikitsa (হোমিওপ্যাথিক পারিবারিক চিকিৎসা), 10th ed. | 1919 | Maheshchandra Bhattacharjya | **test** (held-out) | `in.ernet.dli.2015.352816` |
| bk2 | Homiopyathik Chikitsa Bidhan, Vol. 1 (হোমিওপ্যাথিক চিকিৎসা-বিধান, খন্ড ১) | 1908 | Chandra Shekhar Kali | **train** | `dli.bengal.10689.1338` |

> **Split:** Two books, split by document — **train = bk2 / test = bk1**. Whole books go to one
> split each, so no page is shared across splits. The two books comfortably clear the floor
> (≥ 300 pages, ≥ 60,000 words); threshold tuning uses a held-out slice of bk2 (train).

- **Source (URLs):**
  - bk1 — https://archive.org/details/in.ernet.dli.2015.352816
  - bk2 — https://archive.org/details/dli.bengal.10689.1338
- **Licence / usage rights:** Public domain (bk1 metadata `dc.rights = "In Public Domain"`, DLI /
  JaiGyan; all books published 1908–1919, authors long deceased). Freely re-shareable; we ship a
  download script rather than the raw scans to keep the repo small.
- **Size (to VERIFY after download — A1 estimates):** bk1 alone ≈ 674 pages, djvu.txt ≈ 2.3 MB
  ≈ 120–150k Bengali words; PDF ≈ 33.9 MB, JP2 page-images ≈ 469 MB. Two confirmed books already
  clear the floor (≥ 300 pages, ≥ 60,000 words). **Update these with real counts from the notebook.**
- **Scan / script difficulty:** Bangla যুক্তাক্ষর (conjuncts) and matras break under OCR; 1919
  orthography (ৎ, legacy ya-phala/reph, obsolete codepoints) differs from modern Unicode; mixed
  scripts (Bangla + transliterated Latin remedy names + stray Roman OCR fragments); Bengali
  numerals ০–৯ carry the potencies; faded/foxed and occasionally skewed 600-ppi scans; dense
  footnotes in a smaller register.
- **Split policy (by document, never by page):** whole books to one split each, so no book spans
  two splits — leakage by shared pages is impossible by construction. Near-duplicate remedy
  passages are the residual risk (all books quote the same Materia Medica); checked with
  MinHash/Jaccard across splits, dropping any test chunk with Jaccard > 0.8 vs a train chunk.
