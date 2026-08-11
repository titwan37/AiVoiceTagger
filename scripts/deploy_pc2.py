#!/usr/bin/env python3
"""
scripts/deploy_pc2.py — Safe Deployment Tool for Worker Unit PC2

Deploys the compiled Rust binary, updated watchlist, configs, models, and sidecar
scripts to the PC2 deployment folder WITHOUT damaging or overwriting any existing
database files (aivoicetagger_state.db).

Usage:
    python scripts/deploy_pc2.py [--dest "\\SyNAS\Records\PC-unit2"]
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DEST = Path(r"\\SyNAS\Records\PC-unit2")

def build_rust_release():
    """Build Rust core in release mode."""
    print("🔨 Step 1: Building Rust release binary (cargo build --release)...")
    try:
        res = subprocess.run(
            ["cargo", "build", "--release"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True
        )
        if res.returncode == 0:
            print("  ✅ Rust release binary compiled successfully.")
            return True
        else:
            print(f"  ❌ Cargo build failed:\n{res.stderr}")
            return False
    except Exception as e:
        print(f"  ⚠️ Cargo build invocation warning: {e}")
        return False


def copy_file_safe(src: Path, dest_folder: Path, overwrite: bool = True):
    """Copy a file safely, creating parent folders if needed."""
    if not src.exists():
        print(f"  ⚠️ Skipping missing file: {src}")
        return False

    dest_file = dest_folder / src.name
    dest_folder.mkdir(parents=True, exist_ok=True)

    # NEVER overwrite database files
    if dest_file.suffix.lower() in [".db", ".db-wal", ".db-shm", ".bak"]:
        print(f"  🛡️ PROTECTED DATABASE FILE SKIPPED: {dest_file.name}")
        return False

    shutil.copy2(src, dest_file)
    print(f"  ✅ Copied: {src.name} -> {dest_file}")
    return True


def copy_dir_safe(src_dir: Path, dest_dir: Path):
    """Copy a directory tree safely, protecting database files."""
    if not src_dir.exists():
        print(f"  ⚠️ Skipping missing directory: {src_dir}")
        return

    dest_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for item in src_dir.rglob("*"):
        if item.is_file():
            if item.suffix.lower() in [".db", ".db-wal", ".db-shm", ".bak"]:
                print(f"  🛡️ PROTECTED DATABASE FILE SKIPPED: {item.name}")
                continue
            if "__pycache__" in str(item) or ".git" in str(item):
                continue
            rel_path = item.relative_to(src_dir)
            target = dest_dir / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            copied += 1

    print(f"  ✅ Copied directory tree '{src_dir.name}' ({copied} files) -> {dest_dir}")


def main():
    parser = argparse.ArgumentParser(description="Safely deploy AiVoiceTagger release package to PC2 without touching database files.")
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST, help="Deployment target folder for PC2")
    parser.add_argument("--skip-build", action="store_true", help="Skip cargo build --release step")

    args = parser.parse_args()
    dest_dir = args.dest

    print("=" * 70)
    print("🚀 AiVoiceTagger — PC2 Safe Deployment Tool")
    print(f"   Source Codebase: {BASE_DIR}")
    print(f"   Deployment Dest: {dest_dir}")
    print(f"   Timestamp:       {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # 1. Build Rust Release
    if not args.skip_build:
        build_rust_release()

    release_exe = BASE_DIR / "target" / "release" / "aivoicetagger.exe"
    if not release_exe.exists():
        print(f"❌ Release binary not found at {release_exe}. Run 'cargo build --release' first.")
        sys.exit(1)

    print(f"\n📦 Step 2: Deploying files to {dest_dir} (DATABASE PROTECTED)...")
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Copy Executable
    copy_file_safe(release_exe, dest_dir)

    # Copy Watchlist & Configs
    copy_file_safe(BASE_DIR / "watchlist.txt", dest_dir)
    copy_file_safe(BASE_DIR / "config.yaml", dest_dir)
    copy_file_safe(BASE_DIR / "inventory_manifest.csv", dest_dir)

    # Copy Python scripts & sidecar modules
    copy_dir_safe(BASE_DIR / "scripts", dest_dir / "scripts")
    copy_dir_safe(BASE_DIR / "sidecar", dest_dir / "sidecar")

    # Copy models directory if present
    if (BASE_DIR / "models").exists():
        copy_dir_safe(BASE_DIR / "models", dest_dir / "models")

    # 3. Create PC2 Worker Execution Script (run_pc2.bat)
    run_bat_content = f"""@echo off
echo ==================================================
echo  ⚡ Starting AiVoiceTagger Worker Instance (PC-unit2)
echo ==================================================
aivoicetagger.exe --worker-id PC-unit2 --config config.yaml %*
"""
    run_bat_path = dest_dir / "run_pc2.bat"
    with open(run_bat_path, "w", encoding="utf-8") as f:
        f.write(run_bat_content)
    print(f"  ✅ Created PC2 execution helper: {run_bat_path.name}")

    print("\n" + "=" * 70)
    print("🎉 Deployment to PC2 complete!")
    print("   ✅ Rust binary, configs, watchlist, and scripts deployed.")
    print("   🛡️ All local/network database files were 100% preserved.")
    print(f"   👉 To start PC2 worker: run '{dest_dir}\\run_pc2.bat'")
    print("=" * 70)

if __name__ == "__main__":
    main()
