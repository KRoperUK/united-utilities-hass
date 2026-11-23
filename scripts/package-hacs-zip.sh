#!/usr/bin/env bash
# Build the release asset HACS downloads.
#
# hacs.json sets `zip_release` with `filename: united_utilities.zip`, so HACS
# expects a zip whose *contents* are the integration files at the top level, not
# a nested custom_components/united_utilities/ path.
set -euo pipefail

COMPONENT_DIR="custom_components/united_utilities"
OUTPUT="united_utilities.zip"

if [[ ! -d "$COMPONENT_DIR" ]]; then
  echo "error: $COMPONENT_DIR not found; run from the repository root" >&2
  exit 1
fi

rm -f "$OUTPUT"
(
  cd "$COMPONENT_DIR"
  zip -r -q "../../$OUTPUT" . -x '__pycache__/*' -x '*.pyc' -x '.DS_Store'
)

# Captured once: piping into `grep -q` can SIGPIPE unzip and fail under pipefail.
listing="$(unzip -l "$OUTPUT")"
echo "built $OUTPUT:"
echo "$listing"

if ! grep -q ' manifest.json$' <<<"$listing"; then
  echo "error: manifest.json is not at the root of $OUTPUT" >&2
  exit 1
fi
echo "OK: manifest.json is at the archive root"
