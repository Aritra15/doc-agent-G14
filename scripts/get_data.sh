#!/usr/bin/env bash
# A1/A2 — fetch the scanned corpus (public-domain Bengali homeopathy manuals) into data/raw/.
# Downloads page-IMAGES (JP2) from the Internet Archive / Digital Library of India, unzips them,
# and lays them out as data/raw/<book_id>/*.jp2 so ingest/loader.py can read them.
#
# Raw scans are gitignored — this script is how the corpus is recreated. Run from repo root:
#   bash scripts/get_data.sh
#
# Self-bootstrapping: it installs any missing prerequisite (unzip, pip, the `ia` CLI) itself.
# The Archive items are public, so no login/keys are needed.
set -euo pipefail

# Always operate from the repo root, so relative paths (data/raw/) resolve correctly no matter
# where the script is launched from (repo root, ~, or via an absolute path).
cd "$(dirname "${BASH_SOURCE[0]}")/.." || { echo "!! cannot locate repo root" >&2; exit 1; }
echo ">> Working in: $(pwd)"

# ---------------------------------------------------------------------------
# Prerequisite bootstrap — install anything that's missing.
# ---------------------------------------------------------------------------
SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi

# Install a SYSTEM package with whichever package manager this OS has.
pkg_install() {
  local pkg="$1"
  echo ">> installing system package '$pkg' ..."
  if   command -v apt-get >/dev/null 2>&1; then $SUDO apt-get update -qq && $SUDO apt-get install -y "$pkg"
  elif command -v dnf     >/dev/null 2>&1; then $SUDO dnf install -y "$pkg"
  elif command -v yum     >/dev/null 2>&1; then $SUDO yum install -y "$pkg"
  elif command -v pacman  >/dev/null 2>&1; then $SUDO pacman -Sy --noconfirm "$pkg"
  elif command -v zypper  >/dev/null 2>&1; then $SUDO zypper install -y "$pkg"
  elif command -v apk     >/dev/null 2>&1; then $SUDO apk add --no-cache "$pkg"
  elif command -v brew    >/dev/null 2>&1; then brew install "$pkg"
  else return 1
  fi
}

# Ensure a system command exists (arg2 = package name if it differs from the command).
require_cmd() {
  local cmd="$1" pkg="${2:-$1}"
  command -v "$cmd" >/dev/null 2>&1 && return 0
  echo ">> '$cmd' not found."
  if ! pkg_install "$pkg"; then
    echo "!! Could not auto-install '$cmd'. Please install it manually and re-run." >&2
    exit 1
  fi
  command -v "$cmd" >/dev/null 2>&1 || { echo "!! '$cmd' still missing after install." >&2; exit 1; }
}

# Ensure python3 + pip, then make user-installed console scripts reachable on PATH.
ensure_python_pip() {
  require_cmd python3 python3
  if ! python3 -m pip --version >/dev/null 2>&1; then
    echo ">> pip not found — bootstrapping ..."
    python3 -m ensurepip --upgrade >/dev/null 2>&1 || pkg_install python3-pip || {
      echo "!! Could not install pip. Install python3-pip manually and re-run." >&2; exit 1; }
  fi
  export PATH="$HOME/.local/bin:$PATH"
  local userbin
  userbin="$(python3 -c 'import site,os; print(os.path.join(site.USER_BASE,"bin"))' 2>/dev/null || true)"
  [ -n "$userbin" ] && export PATH="$userbin:$PATH"
}

# Install a PYTHON package, tolerating PEP-668 "externally managed" environments.
pip_install() {
  local pkg="$1"
  python3 -m pip install --quiet "$pkg" 2>/dev/null \
    || python3 -m pip install --quiet --user "$pkg" 2>/dev/null \
    || python3 -m pip install --quiet --user --break-system-packages "$pkg"
}

echo ">> Checking prerequisites ..."
require_cmd unzip unzip
ensure_python_pip
if ! command -v ia >/dev/null 2>&1; then
  echo ">> Internet Archive CLI not found — installing 'internetarchive' ..."
  pip_install internetarchive
fi
command -v ia >/dev/null 2>&1 || { echo "!! 'ia' still not on PATH after install." >&2; exit 1; }
echo ">> Prerequisites OK."

# ---------------------------------------------------------------------------
# Download the corpus.
# ---------------------------------------------------------------------------
RAW="data/raw"
mkdir -p "$RAW"

# book_id -> archive.org identifier  (see data/provenance.md). Two books, split by document:
# bk2 = train, bk1 = test (held-out).
declare -A BOOKS=(
  ["bk1"]="in.ernet.dli.2015.352816"   # Bhattacharjya 1919 — test (held-out)
  ["bk2"]="dli.bengal.10689.1338"      # Kali 1908 — train
)

for book_id in "${!BOOKS[@]}"; do
  identifier="${BOOKS[$book_id]}"
  dest="$RAW/$book_id"
  # Skip only if PAGE-IMAGES are already there (a pdf-only folder must still fetch the JP2s).
  if [ -d "$dest" ] && find "$dest" -maxdepth 1 -type f \
       \( -iname '*.jp2' -o -iname '*.jpg' -o -iname '*.png' \) | grep -q .; then
    echo ">> $book_id ($identifier) page-images already present in $dest — skipping."
    continue
  fi
  mkdir -p "$dest"
  echo ">> Downloading $book_id  <-  archive.org/details/$identifier"

  # Download the JP2 page-image archive — the real source the pipeline reads (loader -> OCR).
  ia download "$identifier" --glob="*_jp2.zip" --destdir "$dest" --no-directories || true

  # Unzip the JP2 bundle flat into the folder, then drop the zip.
  shopt -s nullglob
  for z in "$dest"/*_jp2.zip; do
    echo "   unzipping $(basename "$z") ..."
    unzip -q -o -j "$z" -d "$dest"
    rm -f "$z"
  done
  shopt -u nullglob

  n=$(find "$dest" -type f \( -iname '*.jp2' -o -iname '*.jpg' -o -iname '*.png' -o -iname '*.pdf' \) | wc -l)
  echo "   -> $n files in $dest"
done

echo ">> Done. Corpus is in $RAW/. Verify page/word counts in notebooks/eda.ipynb."
