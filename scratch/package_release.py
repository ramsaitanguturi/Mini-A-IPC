import os
import shutil
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RELEASE_DIR = os.path.join(ROOT, "release")
ZIP_PATH = os.path.join(RELEASE_DIR, "Mini-A-IPC-v2.0-Final-Submission.zip")

os.makedirs(RELEASE_DIR, exist_ok=True)

# Patterns / files to explicitly exclude
EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".tmp_versions",
    "scratch",
    "release",
}

EXCLUDE_EXTS = {
    ".o", ".obj", ".exe", ".ko", ".mod", ".mod.c", ".mod.o",
    ".order", ".symvers", ".pyc", ".pyo"
}

EXCLUDE_NAMES = {
    "Thumbs.db", ".DS_Store", "desktop.ini"
}

import hashlib

# Explicitly ensure clean tracked files or necessary data files
print(f"Creating release archive: {ZIP_PATH}")
with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
    for dirpath, dirnames, filenames in os.walk(ROOT):
        # Exclude directories in-place
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not d.startswith(".")]

        rel_dir = os.path.relpath(dirpath, ROOT)
        if rel_dir == ".":
            rel_dir = ""

        for fname in filenames:
            if fname in EXCLUDE_NAMES:
                continue
            _, ext = os.path.splitext(fname)
            if ext.lower() in EXCLUDE_EXTS:
                continue
            # Also exclude compiled binaries with no extension if in root or bin
            if ext == "" and fname in {"mini-aipc", "mini-aipc-concurrency", "mini-aipc-mixed", "aipc-client", "ipc_fifo", "aipc_unified_bench"}:
                continue

            full_path = os.path.join(dirpath, fname)
            arcname = os.path.join("Mini-A-IPC", rel_dir, fname).replace("\\", "/")
            zf.write(full_path, arcname)

# Compute SHA256
sha256 = hashlib.sha256()
with open(ZIP_PATH, "rb") as f:
    for chunk in iter(lambda: f.read(65536), b""):
        sha256.update(chunk)
digest = sha256.hexdigest().upper()

sums_path = os.path.join(RELEASE_DIR, "SHA256SUMS")
with open(sums_path, "w", encoding="utf-8") as f:
    f.write(f"{digest}  {os.path.basename(ZIP_PATH)}\n")

print("Release archive created successfully!")
print(f"Archive size: {os.path.getsize(ZIP_PATH):,} bytes")
print(f"SHA-256: {digest}")

