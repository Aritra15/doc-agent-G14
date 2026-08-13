#!/usr/bin/env bash
# A1/A2 — fetch the scanned corpus (public-domain Bengali homeopathy manuals) into data/raw/.
# Downloads page-IMAGES (JP2) from the Internet Archive / Digital Library of India, unzips them,
# converts them to PNG (universal + lossless), and lays them out as data/raw/<book_id>/*.png
# so ingest/loader.py — and every teammate's toolchain — can read them without OpenJPEG surprises.
#
# Raw scans are gitignored — this script is how the corpus is recreated. Run from repo root:
#   bash scripts/get_data.sh
#
# Self-bootstrapping: it installs any missing prerequisite (unzip, pip, the `ia` CLI, Pillow) itself.
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
PYTHON_BIN=""

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
  # Windows Git Bash may expose an unusable Microsoft Store `python3` shim, while the real
  # interpreter is named `python`. Test execution instead of trusting command -v alone.
  if command -v python3 >/dev/null 2>&1 && python3 --version >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1 && python --version >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    pkg_install python3 || {
      echo "!! Could not install Python. Install Python 3 manually and re-run." >&2; exit 1; }
    PYTHON_BIN="python3"
  fi
  if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
    echo ">> pip not found — bootstrapping ..."
    "$PYTHON_BIN" -m ensurepip --upgrade >/dev/null 2>&1 || pkg_install python3-pip || {
      echo "!! Could not install pip. Install python3-pip manually and re-run." >&2; exit 1; }
  fi
  export PATH="$HOME/.local/bin:$PATH"
  local userbin
  userbin="$("$PYTHON_BIN" -c 'import os,sysconfig; scheme="nt_user" if os.name=="nt" else "posix_user"; print(sysconfig.get_path("scripts", scheme=scheme))' 2>/dev/null || true)"
  if [ -n "$userbin" ] && command -v cygpath >/dev/null 2>&1; then
    userbin="$(cygpath -u "$userbin")"
  fi
  [ -n "$userbin" ] && export PATH="$userbin:$PATH"
}

# Install a PYTHON package, tolerating PEP-668 "externally managed" environments.
pip_install() {
  local pkg="$1"
  "$PYTHON_BIN" -m pip install --quiet "$pkg" 2>/dev/null \
    || "$PYTHON_BIN" -m pip install --quiet --user "$pkg" 2>/dev/null \
    || "$PYTHON_BIN" -m pip install --quiet --user --break-system-packages "$pkg"
}

# Convert every *.jp2 in a folder to *.png (lossless) and drop the JP2 once its PNG exists.
# JP2s are re-fetchable via this script, so PNG becomes the working page-image format.
jp2_to_png() {
  local dir="$1"
  "$PYTHON_BIN" - "$dir" <<'PY'
import sys, pathlib
from PIL import Image
d = pathlib.Path(sys.argv[1])
converted = 0
for p in sorted(d.glob("*.jp2")):
    png = p.with_suffix(".png")
    try:
        if not png.exists():
            with Image.open(p) as im:
                im.save(png)
            converted += 1
        p.unlink()  # remove the JP2 once its PNG exists
    except Exception as e:
        print(f"   !! convert failed {p.name}: {e}", file=sys.stderr)
print(f"   converted {converted} JP2 -> PNG  ({len(list(d.glob('*.png')))} PNG total in {d})")
PY
}

echo ">> Checking prerequisites ..."
require_cmd unzip unzip
ensure_python_pip
if ! command -v ia >/dev/null 2>&1; then
  echo ">> Internet Archive CLI not found — installing 'internetarchive' ..."
  pip_install internetarchive
fi
command -v ia >/dev/null 2>&1 || { echo "!! 'ia' still not on PATH after install." >&2; exit 1; }
# Pillow (with JPEG-2000 support) for the JP2 -> PNG conversion.
if ! "$PYTHON_BIN" -c "import PIL" 2>/dev/null; then
  echo ">> Pillow not found — installing (for JP2 -> PNG conversion) ..."
  pip_install pillow
fi
if ! "$PYTHON_BIN" -c "import sys; from PIL import features; sys.exit(0 if features.check('jpg_2000') else 1)" 2>/dev/null; then
  echo "!! Pillow has no JPEG-2000 support. Install system OpenJPEG (e.g. '$SUDO apt-get install -y libopenjp2-7')" >&2
  echo "!! then reinstall Pillow:  python3 -m pip install --force-reinstall pillow" >&2
  exit 1
fi
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
  mkdir -p "$dest"

  # Already fully processed if PNG page-images exist — skip.
  if find "$dest" -maxdepth 1 -type f -iname '*.png' | grep -q .; then
    echo ">> $book_id ($identifier) PNG page-images already present in $dest — skipping."
    continue
  fi

  # Download + unzip only if the JP2s aren't already here (e.g. a prior run stopped mid-convert).
  if ! find "$dest" -maxdepth 1 -type f -iname '*.jp2' | grep -q .; then
    echo ">> Downloading $book_id  <-  archive.org/details/$identifier"
    # JP2 page-image archive — the real source the pipeline reads (loader -> OCR).
    ia download "$identifier" --glob="*_jp2.zip" --destdir "$dest" --no-directories || true
    shopt -s nullglob
    for z in "$dest"/*_jp2.zip; do
      echo "   unzipping $(basename "$z") ..."
      unzip -q -o -j "$z" -d "$dest"
      rm -f "$z"
    done
    shopt -u nullglob
  fi

  # Convert JP2 -> PNG (lossless) so the corpus is a set of universally-readable *.png.
  jp2_to_png "$dest"

  n=$(find "$dest" -type f -iname '*.png' | wc -l)
  echo "   -> $n PNG page-images in $dest"
done

echo ">> Done. Corpus is in $RAW/. Verify page/word counts in notebooks/eda.ipynb."
