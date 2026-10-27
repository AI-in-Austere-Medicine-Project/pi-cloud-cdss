#!/bin/bash
# S1: speech in. Build pywhispercpp (whisper.cpp) for this Jetson's GPU and
# put the base.en weights on disk. The one speech-in step that needs the
# network; after it, /transcribe makes no connection.
#
#   bash server/tools/install_whisper.sh [python] [dir]
#     python  the service venv's (default: <repo>/.venv/bin/python)
#     dir     the weights' directory (default: server/data/whisper)
#
# Needs the CUDA toolkit (nvcc, JetPack's /usr/local/cuda), cmake and a C++
# compiler. The build compiles whisper.cpp's CUDA kernels for sm_87 (Orin);
# allow 20-40 minutes on the Jetson.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${1:-$HERE/../../.venv/bin/python}"
DIR="${2:-$HERE/../data/whisper}"
PYWHISPERCPP=1.5.1          # bundles whisper.cpp 1.8.5
PLATFORMDIRS=4.3.6          # pywhispercpp imports it; requests and tqdm are already in the venv

mkdir -p "$DIR"
cd "$DIR"
while read -r sum file; do
  if [ ! -s "$file" ]; then
    curl -fSL -o "$file.part" "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$file"
    mv "$file.part" "$file"
  fi
  echo "$sum  $file" | sha256sum -c -
done <<'SUMS'
a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002 ggml-base.en.bin
SUMS

# pywhispercpp's setup.py passes EVERY environment variable to CMake as -D,
# so the build runs in a clean environment with only what it needs.
env -i PATH=/usr/local/cuda/bin:/usr/bin:/bin HOME="$HOME" \
  CUDACXX=/usr/local/cuda/bin/nvcc GGML_CUDA=1 CMAKE_CUDA_ARCHITECTURES=87 \
  "$PY" -m pip install --no-deps --no-cache-dir --no-binary pywhispercpp \
  "pywhispercpp==$PYWHISPERCPP" "platformdirs==$PLATFORMDIRS"

# The build leaves each library's RUNPATH at pip's deleted build directory in
# /tmp, so the extension cannot find libwhisper.so.1 beside it (ImportError),
# and anyone who recreated that directory could plant a library the service
# loads. Point them at $ORIGIN (their own directory, site-packages) instead,
# with patchelf from a throwaway venv. Idempotent: rerunning the script on an
# installed package only redoes this.
SITE="$("$PY" -c "import sysconfig; print(sysconfig.get_paths()['purelib'])")"
PE="$(mktemp -d)"
trap 'rm -rf "$PE"' EXIT
python3 -m venv "$PE/venv"
"$PE/venv/bin/pip" install -q --only-binary :all: patchelf==0.17.2.1
for f in "$SITE"/_pywhispercpp*.so "$SITE"/libwhisper.so* "$SITE"/libggml*.so*; do
  "$PE/venv/bin/patchelf" --set-rpath '$ORIGIN' "$f"
done

"$PY" -c "import pywhispercpp.model, sys; print('pywhispercpp', pywhispercpp.model.__version__, 'importable')"
echo "whisper weights verified in $DIR"
