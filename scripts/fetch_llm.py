"""Download Qwen2.5-0.5B-Instruct Q4_K_M into model_cache/ and check it (docs/rag.md).

    python scripts/fetch_llm.py            download if missing, then verify size and SHA-256
    python scripts/fetch_llm.py --check    only verify the file already there
    python scripts/fetch_llm.py --cache C:\\Users\\me\\pathgen-models   keep it outside OneDrive or Dropbox

The cache can also come from LLM_CACHE_DIR. The file stays out of Git (.gitignore: model_cache/,
*.gguf). Run llama.cpp's server on it with:

    llama-server -m model_cache/qwen2.5-0.5b-instruct-q4_k_m.gguf --host 127.0.0.1 --port 8080 -c 2048
"""
import argparse
import hashlib
import os
import sys
import urllib.request
from pathlib import Path

NAME = "qwen2.5-0.5b-instruct-q4_k_m.gguf"
REVISION = "9217f5db79a29953eb74d5343926648285ec7e67"
URL = f"https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/{REVISION}/{NAME}"
SIZE = 491_400_032
SHA256 = "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db"
CACHE = Path(__file__).resolve().parent.parent / "model_cache"


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(path):
    if not path.exists():
        return f"{path} is missing."
    if path.stat().st_size != SIZE:
        return f"{path} has {path.stat().st_size:,} bytes, expected {SIZE:,}."
    if sha256_of(path) != SHA256:
        return f"{path} doesn't match the expected SHA-256."
    return None


def download(path):
    partial = path.with_suffix(".part")
    start = partial.stat().st_size if partial.exists() else 0
    request = urllib.request.Request(URL, headers={"Range": f"bytes={start}-"} if start else {})
    with urllib.request.urlopen(request, timeout=60) as response, open(partial, "ab" if start else "wb") as out:
        if start and response.status != 206:
            out.truncate(0)
        done = start
        while block := response.read(1 << 20):
            out.write(block)
            done += len(block)
            print(f"\r{done / SIZE:6.1%}", end="", flush=True)
    print()
    partial.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="only verify the cached file")
    parser.add_argument("--cache", default=os.environ.get("LLM_CACHE_DIR") or str(CACHE),
                        help="folder for the model file (default: model_cache/ in the project)")
    args = parser.parse_args()
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / NAME
    if not args.check and verify(path):
        print(f"Downloading {NAME} ({SIZE / 1e6:.0f} MB) from the official Qwen repository...")
        download(path)
    problem = verify(path)
    if problem:
        print(problem, file=sys.stderr)
        return 1
    print(f"OK: {path} (SHA-256 {SHA256[:12]}...)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
