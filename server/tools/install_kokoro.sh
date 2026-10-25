#!/bin/bash
# V2: put the Kokoro-82M weights and voices on disk for /speak. The one voice
# step that needs the network; after it, voice makes no connection.
#
#   bash server/tools/install_kokoro.sh [dir]     (default: server/data/kokoro)
#
# Also needs: sudo apt install espeak-ng   and   pip install kokoro-onnx==0.6.1
set -euo pipefail
DIR="${1:-$(cd "$(dirname "$0")/.." && pwd)/data/kokoro}"
BASE=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
mkdir -p "$DIR"
cd "$DIR"
while read -r sum file; do
  if [ ! -s "$file" ]; then
    curl -fSL -o "$file.part" "$BASE/$file"
    mv "$file.part" "$file"
  fi
  echo "$sum  $file" | sha256sum -c -
done <<'SUMS'
7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5 kokoro-v1.0.onnx
bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d voices-v1.0.bin
SUMS
echo "Kokoro files verified in $DIR"
