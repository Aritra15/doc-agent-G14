#!/usr/bin/env bash
# A2 — build the complete knowledge base exactly once.
set -euo pipefail
make index
# python scripts/run_index.py
