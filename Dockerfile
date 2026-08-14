FROM python:3.11-slim
WORKDIR /app

# System dependency: Tesseract OCR + Bengali language data.
# The pipeline shells out to the `tesseract` binary (vision/layout.py, vision/ocr.py),
# which is NOT a pip package — without this the OCR stage cannot run.
RUN apt-get update && apt-get install -y --no-install-recommends \
      tesseract-ocr tesseract-ocr-ben \
    && rm -rf /var/lib/apt/lists/*

# Pinned Python dependencies. Generate the lockfile before building:
#   uv pip compile pyproject.toml -o requirements.lock
COPY pyproject.toml requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY . .
# src/ layout: make the `doc_agent` package importable without installing it.
ENV PYTHONPATH=/app/src

EXPOSE 8000
CMD ["uvicorn", "doc_agent.serve.api:app", "--host", "0.0.0.0", "--port", "8000"]
