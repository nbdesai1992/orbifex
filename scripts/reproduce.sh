#!/usr/bin/env bash
# Rebuild the seed-7 dataset, compare it with the published archive, and print the results.
#
#     scripts/reproduce.sh [PYTHON]        # PYTHON defaults to python3.11; the package needs 3.11 or newer
#
# What it does, in order:
#   1. Regenerates the cpa-solo workspace at seed 7 with the README's `ladder` command, into a
#      temporary folder.
#   2. Prints one sha256 for the generated task tree (scripts/tree_sha256.py says how it is formed).
#   3. Downloads the published archive, unpacks it and compares the two trees file by file.
#      Set ORBIFEX_ARCHIVE to a local copy of the archive to skip the download.
#   4. Compares the regenerated gate reports with the ones committed beside the pilot records.
#   5. Prints the results table and the headline numbers from the committed JSONL files.
#
# No model is called and nothing is written outside the temporary folder. Needs curl and tar.
# The exit status is 0 only if every comparison was made and every one matched.
set -euo pipefail

PY="${1:-python3.11}"
ARCHIVE_URL="https://nealdes.ai/assets/orbifex/cpa-solo-harbor-v2.tar.gz"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RESULTS="$ROOT/experiments/results/cpa-solo-seed7-v2"

if ! command -v "$PY" >/dev/null 2>&1; then
  echo "reproduce: '$PY' was not found. Pass a Python 3.11 or newer interpreter as the first argument." >&2
  exit 2
fi
if ! "$PY" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
  echo "reproduce: $("$PY" --version 2>&1) is too old. The package needs Python 3.11 or newer." >&2
  exit 2
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
status=0
cd "$ROOT"
export PYTHONDONTWRITEBYTECODE=1

echo "== 1. Regenerate cpa-solo at seed 7 with $("$PY" --version 2>&1)"
PYTHONPATH=src "$PY" -m orbifex.cli ladder personas/cpa-solo.toml --seed 7 \
    --out "$TMP/build" --workspace --harbor "$TMP/datasets"

echo
echo "== 2. Checksum of the generated task tree"
generated="$("$PY" -I scripts/tree_sha256.py "$TMP/datasets" --match 'cpa-solo-t*')"
echo "generated  $generated"

echo
echo "== 3. Compare with the published archive"
mkdir "$TMP/published"
if [ -n "${ORBIFEX_ARCHIVE:-}" ]; then
  echo "using the local copy $ORBIFEX_ARCHIVE"
  cp "$ORBIFEX_ARCHIVE" "$TMP/archive.tar.gz"
elif ! curl -fsSL --retry 2 -o "$TMP/archive.tar.gz" "$ARCHIVE_URL"; then
  echo "NOT COMPARED: could not download $ARCHIVE_URL"
  status=1
fi
if [ -f "$TMP/archive.tar.gz" ]; then
  tar -xzf "$TMP/archive.tar.gz" -C "$TMP/published"
  published="$("$PY" -I scripts/tree_sha256.py "$TMP/published" --match 'cpa-solo-t*')"
  echo "published  $published"
  if "$PY" -I scripts/tree_sha256.py "$TMP/datasets" --compare "$TMP/published" --match 'cpa-solo-t*'; then
    echo "The regenerated task tree is file for file identical to the published archive."
  else
    echo "DIFFERENT: the files listed above differ (first tree is the regeneration, second is the archive)."
    status=1
  fi
  extra="$(cd "$TMP/published" && find . -maxdepth 1 -type f | sed 's|^\./||' | LC_ALL=C sort | tr '\n' ' ')"
  echo "Files in the archive that the generator does not write: ${extra:-none}"
fi

echo
echo "== 4. Compare the regenerated gate reports with the committed ones"
for tier in 1 2 3 4; do
  if cmp -s "$TMP/build/t$tier/report.json" "$RESULTS/report-t$tier.json"; then
    echo "report-t$tier.json  identical"
  else
    echo "report-t$tier.json  DIFFERENT from $TMP/build/t$tier/report.json"
    status=1
  fi
done
if cmp -s "$TMP/build/ladder.json" "$RESULTS/ladder.json"; then
  echo "ladder.json     identical"
else
  echo "ladder.json     DIFFERENT"
  status=1
fi

echo
echo "== 5. Results, counted from experiments/results/"
"$PY" scripts/results_table.py
echo
"$PY" scripts/results_table.py --policies
echo
"$PY" scripts/results_table.py --facts --build "$TMP/build"

echo
if [ "$status" -eq 0 ]; then
  echo "All comparisons matched."
else
  echo "At least one comparison failed or was not made. See above."
fi
exit "$status"
