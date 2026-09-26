#!/bin/bash
# Runs ON THE JETSON, called by `make ship` after the Q4 file has been copied.
# Usage: ship_remote.sh <tag> <base-model>
#
# The Modelfile takes TEMPLATE, SYSTEM and LICENSE from the base model, so the
# new tag differs from the base in its weights only, and a before/after bench
# compares weights, not prompt formats.
set -euo pipefail
TAG=$1 BASE=$2
DIR=$HOME/edgecdss-models
GGUF=$DIR/$TAG-q4km.gguf
MF=$DIR/Modelfile.$TAG

[ -f "$GGUF" ] || { echo "ship: $GGUF missing" >&2; exit 2; }
ollama show "$BASE" --template >/dev/null || { echo "ship: base $BASE not in ollama" >&2; exit 2; }

{
  echo "FROM $GGUF"
  printf 'TEMPLATE """%s"""\n' "$(ollama show "$BASE" --template)"
  printf 'SYSTEM """%s"""\n' "$(ollama show "$BASE" --system)"
  printf 'LICENSE """%s"""\n' "$(ollama show "$BASE" --license)"
} > "$MF"

ollama create "$TAG" -f "$MF" > "$DIR/create-$TAG.log" 2>&1 \
  || { tail -5 "$DIR/create-$TAG.log" >&2; exit 2; }
# Ollama keeps its own copy in its blob store.
rm -f "$GGUF"

for part in template system; do
  diff <(ollama show "$TAG" --$part) <(ollama show "$BASE" --$part) >/dev/null \
    || { echo "ship: $TAG $part differs from $BASE" >&2; exit 2; }
done
echo "ship: created $TAG ($(ollama list | awk -v t="$TAG:latest" '$1==t {print $2, $3, $4}')), template and system identical to $BASE"
