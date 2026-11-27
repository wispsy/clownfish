#!/usr/bin/env python3
"""Automate publishing Homebrew Formula and Cask to wispsy/homebrew-tap."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = REPO_ROOT / "dist"
PACKAGING_DIR = REPO_ROOT / "packaging" / "homebrew"
DEFAULT_TAP_REPO = "wispsy/homebrew-tap"


def get_version() -> str:
    """Read version from src/clownfish/__init__.py."""
    init_file = REPO_ROOT / "src" / "clownfish" / "__init__.py"
    with open(init_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("__version__"):
                return line.split("=")[1].strip().strip('"').strip("'")
    return "0.7.0"


def calculate_sha256(path: Path) -> str:
    """Calculate SHA256 of a local file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def render_formula(version: str, sha256: str) -> str:
    """Render Formula/clownfish.rb content."""
    return f"""class Clownfish < Formula
  include Language::Python::Virtualenv

  desc "Lightweight, zero-dependency modern terminal emulator"
  homepage "https://github.com/wispsy/clownfish"
  url "https://files.pythonhosted.org/packages/source/c/clownfish/clownfish-{version}.tar.gz"
  sha256 "{sha256}"
  license "MIT"

  depends_on "python@3.14"
  depends_on "python-tk@3.14"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "clownfish {version}", shell_output("#{{bin}}/clownfish --version")
    system libexec/"bin/python", "-c", "import tkinter; import clownfish"
  end
end
"""


def render_cask(version: str, sha256: str) -> str:
    """Render Casks/clownfish.rb content."""
    return f"""cask "clownfish" do
  version "{version}"
  sha256 "{sha256}"

  url "https://github.com/wispsy/clownfish/releases/download/v#{{version}}/Clownfish-v#{{version}}-macos.zip"
  name "Clownfish"
  desc "Lightweight, zero-dependency modern terminal emulator"
  homepage "https://github.com/wispsy/clownfish"

  app "Clownfish.app"
  binary "#{{appdir}}/Clownfish.app/Contents/MacOS/Clownfish", target: "clownfish"

  zap trash: [
    "~/.config/clownfish",
    "~/Library/Saved Application State/tech.wispsy.clownfish.savedState",
  ]
end
"""


def publish_to_tap(
    tap_repo: str,
    formula_content: str,
    cask_content: str,
    version: str,
    dry_run: bool = False,
) -> None:
    """Commit and push updated formula and cask to the tap repository."""
    print(f"Target tap: {tap_repo}")
    if dry_run:
        print("\n--- [DRY RUN] Formula/clownfish.rb ---")
        print(formula_content)
        print("\n--- [DRY RUN] Casks/clownfish.rb ---")
        print(cask_content)
        print("\nDry run completed. No remote changes made.")
        return

    with tempfile.TemporaryDirectory() as tmp_dir:
        clone_url = f"https://github.com/{tap_repo}.git"
        print(f"Cloning {clone_url}...")
        subprocess.run(["git", "clone", clone_url, tmp_dir], check=True)

        formula_dir = Path(tmp_dir) / "Formula"
        cask_dir = Path(tmp_dir) / "Casks"
        formula_dir.mkdir(parents=True, exist_ok=True)
        cask_dir.mkdir(parents=True, exist_ok=True)

        formula_file = formula_dir / "clownfish.rb"
        cask_file = cask_dir / "clownfish.rb"

        formula_file.write_text(formula_content, encoding="utf-8")
        cask_file.write_text(cask_content, encoding="utf-8")

        # Also update in local packaging directory for tracking
        (PACKAGING_DIR / "Formula" / "clownfish.rb").write_text(formula_content, encoding="utf-8")
        (PACKAGING_DIR / "Casks" / "clownfish.rb").write_text(cask_content, encoding="utf-8")

        status_res = subprocess.run(
            ["git", "-C", tmp_dir, "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        if not status_res.stdout.strip():
            print("No changes to publish in tap repository.")
            return

        subprocess.run(["git", "-C", tmp_dir, "add", "Formula", "Casks"], check=True)
        commit_msg = f"feat(clownfish): update to v{version}"
        subprocess.run(
            ["git", "-C", tmp_dir, "commit", "-m", commit_msg],
            check=True,
        )
        print(f"Pushing updates to {tap_repo}...")
        push_res = subprocess.run(
            ["git", "-C", tmp_dir, "push", "origin", "main"],
            check=False,
            capture_output=True,
            text=True,
        )
        if push_res.returncode == 0:
            print("✅ Successfully published to Homebrew tap via direct push!")
            return

        print("Direct push to main declined (protected branch). Creating pull request...")
        branch_name = f"feat/clownfish-v{version}"
        subprocess.run(["git", "-C", tmp_dir, "checkout", "-b", branch_name], check=True)
        subprocess.run(["git", "-C", tmp_dir, "push", "-u", "origin", branch_name], check=True)
        pr_cmd = [
            "gh", "pr", "create",
            "--repo", tap_repo,
            "--base", "main",
            "--head", branch_name,
            "--title", commit_msg,
            "--body", f"Automated Homebrew formula and cask update for Clownfish v{version}.",
        ]
        subprocess.run(pr_cmd, check=True)
        print("✅ Pull request created for Homebrew tap!")


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish Clownfish to wispsy/homebrew-tap")
    parser.add_argument("--version", default=get_version(), help="Release version")
    parser.add_argument("--tap", default=DEFAULT_TAP_REPO, help="Target Homebrew tap repository")
    parser.add_argument("--tar-sha256", help="SHA256 of clownfish source tarball")
    parser.add_argument("--zip-sha256", help="SHA256 of Clownfish macOS zip archive")
    parser.add_argument("--dry-run", action="store_true", help="Print formulas without pushing")
    args = parser.parse_args()

    version = args.version
    tar_path = DIST_DIR / f"clownfish-{version}.tar.gz"
    zip_path = DIST_DIR / f"Clownfish-v{version}-macos.zip"

    tar_sha = args.tar_sha256
    if not tar_sha:
        if tar_path.exists():
            tar_sha = calculate_sha256(tar_path)
            print(f"Calculated sdist sha256: {tar_sha}")
        else:
            sys.exit(f"Error: {tar_path} not found and --tar-sha256 not provided.")

    zip_sha = args.zip_sha256
    if not zip_sha:
        if zip_path.exists():
            zip_sha = calculate_sha256(zip_path)
            print(f"Calculated macOS zip sha256: {zip_sha}")
        else:
            sys.exit(f"Error: {zip_path} not found and --zip-sha256 not provided.")

    formula_content = render_formula(version, tar_sha)
    cask_content = render_cask(version, zip_sha)

    publish_to_tap(args.tap, formula_content, cask_content, version, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
