#!/usr/bin/env python3
"""W1: install the Pocket code /pocket runs, at the commit server/pocket_pin.json pins.

    python3 server/tools/install_pocket.py [--models]

Clones the edgecdss-pocket repo into $POCKET_HOME (default ~/pocket-web) as
edgecdss-pocket-<commit[:12]> and checks out the pinned commit, detached. With
--models, also downloads the Vosk model and the Piper voice the pin names and checks
their sha256. Nothing is written inside this repository.

The Python packages are requirements-pocket.txt. On the Jetson, install them with
--no-deps: piper-tts depends on onnxruntime, and pip would replace the Jetson's
onnxruntime-gpu build with the CPU wheel.
"""
import argparse
import hashlib
import pathlib
import shutil
import subprocess
import sys
import urllib.request
import zipfile

_SERVER = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVER))

import pocket_web as pw  # noqa: E402


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _fetch(url: str, dest: pathlib.Path, sha256: str = "") -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    if sha256 and _sha256(tmp) != sha256:
        tmp.unlink()
        raise SystemExit(f"REFUSED: {url} does not match its pinned sha256")
    tmp.replace(dest)


def install_code() -> pathlib.Path:
    dest = pw.checkout_dir()
    if not (dest / ".git").exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", pw.PIN["repo"], str(dest)], check=True)
    subprocess.run(["git", "-C", str(dest), "fetch", "-q", "origin"], check=True)
    subprocess.run(["git", "-C", str(dest), "checkout", "-q", "--detach", pw.PIN["commit"]], check=True)
    pw.verify_checkout(dest)
    return dest


def install_models() -> None:
    vosk = pw.vosk_model_dir()
    if not vosk.exists():
        vosk.parent.mkdir(parents=True, exist_ok=True)
        z = vosk.parent / (vosk.name + ".zip")
        _fetch(pw.PIN["vosk_model"]["url"], z, pw.PIN["vosk_model"]["zip_sha256"])
        with zipfile.ZipFile(z) as zf:
            zf.extractall(vosk.parent)
        z.unlink()
    onnx = pw.piper_voice_path()
    onnx.parent.mkdir(parents=True, exist_ok=True)
    base = pw.PIN["piper_voice"]["url_base"]
    if not onnx.exists() or _sha256(onnx) != pw.PIN["piper_voice"]["onnx_sha256"]:
        _fetch(f"{base}/{onnx.name}", onnx, pw.PIN["piper_voice"]["onnx_sha256"])
    cfg = onnx.with_name(onnx.name + ".json")
    if not cfg.exists():
        _fetch(f"{base}/{cfg.name}", cfg)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--models", action="store_true", help="also fetch the Vosk model and Piper voice")
    a = ap.parse_args(argv)
    try:
        print(f"Pocket {pw.PIN['commit'][:12]} at {install_code()}")
        if a.models:
            install_models()
            print(f"models at {pw.vosk_model_dir().parent}")
    except pw.Unavailable as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
