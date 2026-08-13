# A2 Pipeline and Script Guide

This guide describes the current scripts and the commands needed on Windows PowerShell to
download the books and build the searchable A2 knowledge base.

## Files in `scripts/`

- `get_data.sh` — downloads the two Internet Archive JP2 book archives, converts their pages to PNG, and places them in `data/raw/bk1/` and `data/raw/bk2/`.
- `run_ingest.py` — currently calls the complete `build_knowledge_base()` pipeline; it is not ingestion-only yet and therefore does the same work as `run_index.py`.
- `run_index.py` — runs loading, preprocessing, layout detection, OCR, chunking, BGE-M3 embedding, and FAISS index storage in the fixed pipeline order.
- `build_index.sh` — Bash wrapper that calls `run_index.py` once; it is the short A2 build command.
- `set_seed.py` — sets Python, NumPy, and PyTorch seeds inside that process for reproducibility checks.
- `run_eval.py` — reserved for running and scoring `tasks.jsonl`, but its evaluation body is still an A3 placeholder.
- `run.sh` — A3 end-to-end wrapper for the Make targets `seed`, `ingest`, `index`, and `eval`; do not use it for the A2-only build because ingestion and indexing currently repeat the pipeline.

## A2 source changes

### `src/doc_agent/ingest/`

- `loader.py` — recursively discovers supported page images, groups them by book directory, and creates deterministic `Page` IDs such as `bk1_p052`.
- `preprocess.py` — creates fingerprinted PNG caches and supports `passthrough` or configurable classical deskew/denoise/contrast/sharpen/binarization. Passthrough is the measured default because it produced better held-out OCR.

### `src/doc_agent/vision/`

- `layout.py` — calls Tesseract TSV analysis, turns detected blocks into in-bounds heading/text `Region` objects, and uses the full page when no block is found.
- `ocr.py` — OCRs ordered region crops with Bengali and English Tesseract, reconstructs page text, records confidence, and caches one page-level OCR chunk as JSON.

### Related indexing files

- `index/chunk.py` normalizes Unicode and remedy aliases, then creates page-preserving, token-limited chunks; `index/embed.py` creates normalized 1024-dimensional BGE-M3 vectors; `index/store.py` persists and validates the FAISS Flat index and chunk metadata.
- `retrieval/retriever.py` embeds a query with the same model and returns the highest-scoring stored chunks.

## Test changes

The A2 tests now check deterministic page loading, classical and passthrough preprocessing, OCR
assembly/caching, layout fallback, Unicode/remedy-aware chunking, embedding shape, FAISS
save/reload, and top-k retrieval. Expensive external behavior is mocked in unit tests, while the
held-out smoke test separately exercises real Tesseract, BGE-M3, and FAISS on sample pages.

## One-time setup

Run these commands from PowerShell. Python 3.11 and Git for Windows are assumed to be installed.

### 1. Open the repository and create an isolated environment

```powershell
Set-Location "E:\CSE 4.1\CSE 429\doc-agent-template\doc-agent-starter"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The editable installation installs the project requirements, including PyTorch,
SentenceTransformers, Transformers, Pillow dependencies, and `faiss-cpu`. If the environment is
already configured, only activate it.

### 2. Check Tesseract and its Bengali/English language packs

Install Tesseract 5 with the `ben` and `eng` trained-data files first, then verify the installation:

```powershell
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --version
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs
```

Both `ben` and `eng` must appear. The configured executable path is in `configs/config.yaml`.

### 3. Download BGE-M3 to the E drive

Choose the Hugging Face cache location before downloading:

```powershell
New-Item -ItemType Directory -Force "E:\huggingface-cache" | Out-Null
$env:HF_HOME = "E:\huggingface-cache"
python -c "from huggingface_hub import snapshot_download; print(snapshot_download('BAAI/bge-m3'))"
```

The model has already been downloaded on this machine under
`E:\huggingface-cache\hub\models--BAAI--bge-m3\`. Keep setting `HF_HOME` in every new PowerShell
session so `BAAI/bge-m3` is loaded from E instead of the default C-drive cache. To prohibit network
access after the download, also use:

```powershell
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
```

## Complete A2 build, in order

### 1. Activate the environment and set runtime variables

```powershell
Set-Location "E:\CSE 4.1\CSE 429\doc-agent-template\doc-agent-starter"
.\.venv\Scripts\Activate.ps1
$env:HF_HOME = "E:\huggingface-cache"
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
$env:PYTHONPATH = "src"
$env:PYTHONIOENCODING = "utf-8"
```

These commands select the local model cache and make the source package and Bengali terminal
output available to the scripts.

### 2. Fetch and convert both books

```powershell
& "C:\Program Files\Git\bin\bash.exe" scripts/get_data.sh
```

This produces PNG pages under `data/raw/bk1/` and `data/raw/bk2/`. Existing book folders that
already contain PNG files are skipped.

Verify that pages exist:

```powershell
Get-ChildItem data/raw/bk1 -Filter *.png | Measure-Object
Get-ChildItem data/raw/bk2 -Filter *.png | Measure-Object
```

### 3. Build the complete knowledge base and index

```powershell
python scripts/run_index.py
```

Equivalent Git Bash wrapper:

```powershell
& "C:\Program Files\Git\bin\bash.exe" scripts/build_index.sh
```

The build creates or reuses preprocessing and OCR caches, creates normalized chunks, encodes them
with BGE-M3, and rebuilds the persistent FAISS index.

### 4. Verify the generated artifacts

```powershell
Get-ChildItem data/interim/preprocessed
Get-ChildItem data/interim/ocr
Get-Item data/interim/index/index.faiss
Get-Item data/interim/index/chunks.json
python -c "from doc_agent import config; from doc_agent.index import store; i,c=store.load(config.load()); print('vectors=', i.ntotal, 'chunks=', len(c), 'dimension=', i.d)"
```

Generated files remain local and gitignored:

- `data/interim/preprocessed/` — standardized/cached page images and fingerprints.
- `data/interim/ocr/` — page-level OCR text and confidence JSON.
- `data/interim/index/chunks.json` — ordered chunks and index metadata.
- `data/interim/index/index.faiss` — searchable dense-vector index.

### 5. Run a retrieval query

```powershell
python -c "from doc_agent import config; from doc_agent.retrieval.retriever import Retriever; r=Retriever(config.load()); print([(x.id, round(x.score, 4), x.page_ids) for x in r.retrieve('ওলাউঠা dry cholera', 5)])"
```

This embeds the query and prints the five closest chunks with similarity scores and source pages.

### 6. Run the tests

```powershell
python -m pytest
```

This checks the repository contracts and the implemented A2 components. The full-book download and
build can take substantially longer on CPU; Tesseract is CPU-based, and the current PyTorch setup
also uses CPU if CUDA is unavailable.
