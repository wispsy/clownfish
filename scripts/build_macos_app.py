#!/usr/bin/env python3
"""Build and package Clownfish.app for macOS using PyInstaller."""

from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
ASSETS_DIR = REPO_ROOT / "assets"
DIST_DIR = REPO_ROOT / "dist"
BUILD_DIR = REPO_ROOT / "build"
ICON_PNG = SRC_DIR / "clownfish" / "clownfish.png"
ICON_ICNS = ASSETS_DIR / "Clownfish.icns"


def get_version() -> str:
    """Read version from src/clownfish/__init__.py."""
    init_file = SRC_DIR / "clownfish" / "__init__.py"
    with open(init_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("__version__"):
                return line.split("=")[1].strip().strip('"').strip("'")
    return "0.6.3"


def generate_icns() -> Path:
    """Generate Clownfish.icns from clownfish.png using sips and iconutil if needed."""
    if ICON_ICNS.exists():
        return ICON_ICNS

    if not ICON_PNG.exists():
        raise FileNotFoundError(f"Source icon not found at {ICON_PNG}")

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    iconset_dir = ASSETS_DIR / "Clownfish.iconset"
    iconset_dir.mkdir(parents=True, exist_ok=True)

    sizes = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]

    print("Generating macOS iconset from clownfish.png...")
    for dim, filename in sizes:
        dest = iconset_dir / filename
        subprocess.run(
            ["sips", "-z", str(dim), str(dim), str(ICON_PNG), "--out", str(dest)],
            check=True,
            stdout=subprocess.DEVNULL,
        )

    print("Converting iconset to Clownfish.icns...")
    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(ICON_ICNS)],
        check=True,
    )
    shutil.rmtree(iconset_dir)
    print(f"Created {ICON_ICNS}")
    return ICON_ICNS


def build_app(version: str) -> Path:
    """Run PyInstaller to create Clownfish.app."""
    print(f"Building Clownfish.app v{version}...")
    generate_icns()

    spec_file = REPO_ROOT / "Clownfish.spec"
    if spec_file.exists():
        cmd = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(spec_file),
        ]
    else:
        cmd = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--windowed",
            "--name",
            "Clownfish",
            "--osx-bundle-identifier",
            "tech.wispsy.clownfish",
            "--icon",
            str(ICON_ICNS),
            "--paths",
            str(SRC_DIR),
            "--collect-all",
            "clownfish",
            "--add-data",
            f"{ICON_PNG}:clownfish",
            str(SRC_DIR / "clownfish" / "main.py"),
        ]

    print(f"Running command: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)

    app_path = DIST_DIR / "Clownfish.app"
    if not app_path.exists():
        raise RuntimeError(f"Expected bundle not found at {app_path}")

    return app_path


def customize_info_plist(app_path: Path, version: str) -> None:
    """Inject required macOS Info.plist keys for production terminal app."""
    plist_path = app_path / "Contents" / "Info.plist"
    if not plist_path.exists():
        print(f"Warning: {plist_path} not found")
        return

    with open(plist_path, "rb") as f:
        plist_data = plistlib.load(f)

    plist_data["CFBundleDisplayName"] = "Clownfish"
    plist_data["CFBundleName"] = "Clownfish"
    plist_data["CFBundleShortVersionString"] = version
    plist_data["CFBundleVersion"] = version
    plist_data["CFBundleIdentifier"] = "tech.wispsy.clownfish"
    plist_data["NSHighResolutionCapable"] = True
    plist_data["NSRequiresAquaSystemAppearance"] = False
    plist_data["LSApplicationCategoryType"] = "public.app-category.developer-tools"
    plist_data["NSHumanReadableCopyright"] = "Copyright © 2026 Wispsy. MIT License."

    with open(plist_path, "wb") as f:
        plistlib.dump(plist_data, f)
    print(f"Updated Info.plist at {plist_path}")

    # Re-sign the bundle with ad-hoc signature after modifying Info.plist
    print("Re-signing application bundle...")
    subprocess.run(["codesign", "--force", "--deep", "-s", "-", str(app_path)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app_path)], check=True)
    print("Code signature verified successfully.")


def verify_app(app_path: Path, expected_version: str) -> None:
    """Run the built executable to verify integrity."""
    executable = app_path / "Contents" / "MacOS" / "Clownfish"
    if not executable.exists() or not os.access(executable, os.X_OK):
        raise RuntimeError(f"Executable {executable} is missing or not executable")

    print(f"Verifying executable at {executable}...")
    res = subprocess.run([str(executable), "--version"], capture_output=True, text=True, check=True)
    output = res.stdout.strip()
    print(f"Executable version output: {output}")
    if expected_version not in output:
        raise ValueError(f"Expected version {expected_version} in output, got: {output}")

    print("Verifying graphical environment with smoke test...")
    smoke_res = subprocess.run([str(executable), "--smoke-test"], capture_output=True, text=True, check=True)
    if "GUI smoke test passed successfully" not in smoke_res.stdout:
        raise RuntimeError(f"GUI smoke test failed: {smoke_res.stdout} {smoke_res.stderr}")
    print("Graphical environment verified successfully!")
    print("Verification succeeded!")


def create_zip_archive(app_path: Path, version: str) -> Path:
    """Create a distributable zip archive containing Clownfish.app."""
    zip_name = f"Clownfish-v{version}-macos.zip"
    zip_path = DIST_DIR / zip_name
    print(f"Creating zip archive {zip_path}...")
    if zip_path.exists():
        zip_path.unlink()

    # Use ditto on macOS to preserve resource forks, permissions, symlinks, and code signatures
    subprocess.run(
        ["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app_path), str(zip_path)],
        check=True,
    )
    print(f"Created archive: {zip_path} ({zip_path.stat().st_size / (1024 * 1024):.2f} MB)")
    return zip_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build macOS Clownfish.app bundle")
    parser.add_argument("--skip-zip", action="store_true", help="Do not generate zip archive")
    args = parser.parse_args()

    version = get_version()
    app_path = build_app(version)
    customize_info_plist(app_path, version)
    verify_app(app_path, version)

    if not args.skip_zip:
        create_zip_archive(app_path, version)

    print("\n✅ Build complete:")
    print(f"   Bundle:  {app_path}")
    if not args.skip_zip:
        print(f"   Archive: {DIST_DIR / f'Clownfish-v{version}-macos.zip'}")


if __name__ == "__main__":
    main()
