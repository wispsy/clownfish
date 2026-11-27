"""Behavioral tests for CLI packaging, distribution artifacts, and Homebrew integration."""

from __future__ import annotations

import io
import re
import sys
import tomllib
from pathlib import Path
from unittest.mock import patch

import clownfish
from clownfish import main

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_package_version_consistency() -> None:
    """Verify version is consistent across package and metadata."""
    pyproject_path = REPO_ROOT / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        pyproject = tomllib.load(f)
    assert clownfish.__version__ == pyproject["project"]["version"]


def test_cli_version_argument() -> None:
    """Verify clownfish --version prints version and exits cleanly without Tk."""
    stdout_buf = io.StringIO()
    with patch("sys.stdout", stdout_buf):
        main(["--version"])
    output = stdout_buf.getvalue().strip()
    assert output == f"clownfish {clownfish.__version__}"

    stdout_buf = io.StringIO()
    with patch("sys.stdout", stdout_buf):
        main(["-v"])
    assert stdout_buf.getvalue().strip() == f"clownfish {clownfish.__version__}"


def test_cli_help_argument() -> None:
    """Verify clownfish --help prints usage and exits cleanly without Tk."""
    stdout_buf = io.StringIO()
    with patch("sys.stdout", stdout_buf):
        main(["--help"])
    output = stdout_buf.getvalue()
    assert "Usage:" in output
    assert "--version" in output
    assert "--help" in output
    assert "ssh <destination>" in output
    assert "--restore" in output
    assert "--no-restore" in output
    assert "--headless" in output


def test_macos_icon_asset() -> None:
    """Verify assets/Clownfish.icns exists and has valid macOS icon header."""
    icns_path = REPO_ROOT / "assets" / "Clownfish.icns"
    assert icns_path.exists(), "assets/Clownfish.icns must exist"
    assert icns_path.stat().st_size > 100_000, "Icon file should contain high-DPI icon sizes"

    with open(icns_path, "rb") as f:
        header = f.read(4)
    assert header == b"icns", f"Expected 'icns' magic header, got {header!r}"


def test_pyinstaller_spec_and_build_script() -> None:
    """Verify Clownfish.spec and scripts/build_macos_app.py are present and configured."""
    spec_path = REPO_ROOT / "Clownfish.spec"
    assert spec_path.exists()
    spec_content = spec_path.read_text(encoding="utf-8")
    assert "tech.wispsy.clownfish" in spec_content
    assert "Clownfish.app" in spec_content

    build_script = REPO_ROOT / "scripts" / "build_macos_app.py"
    assert build_script.exists()
    script_content = build_script.read_text(encoding="utf-8")
    assert "tech.wispsy.clownfish" in script_content
    assert "customize_info_plist" in script_content


def test_pypi_trusted_publishing_workflow() -> None:
    """Verify .github/workflows/release.yaml contains required PyPI trusted publishing config."""
    release_workflow = REPO_ROOT / ".github" / "workflows" / "release.yaml"
    assert release_workflow.exists(), "Workflow must be named exactly release.yaml"

    workflow_content = release_workflow.read_text(encoding="utf-8")
    # Verify environment parameter as required by PyPI trusted publisher
    assert "name: pypi" in workflow_content
    # Verify OIDC token permission
    assert "id-token: write" in workflow_content
    # Verify official pypi publish action
    assert re.search(r"pypa/gh-action-pypi-publish@[0-9a-f]{40}", workflow_content)
    # Verify macOS bundle build step is included
    assert "build_macos_app.py" in workflow_content
    assert "Clownfish-*-macos.zip" in workflow_content


def test_homebrew_tap_packaging_artifacts() -> None:
    """Verify Formula and Cask templates for wispsy/homebrew-tap exist."""
    formula_path = REPO_ROOT / "packaging" / "homebrew" / "Formula" / "clownfish.rb"
    assert formula_path.exists()
    formula_content = formula_path.read_text(encoding="utf-8")
    assert "class Clownfish < Formula" in formula_content

    cask_path = REPO_ROOT / "packaging" / "homebrew" / "Casks" / "clownfish.rb"
    assert cask_path.exists()
    cask_content = cask_path.read_text(encoding="utf-8")
    assert 'cask "clownfish" do' in cask_content
    assert 'app "Clownfish.app"' in cask_content

    publish_script = REPO_ROOT / "scripts" / "publish_homebrew.py"
    assert publish_script.exists()


def test_homebrew_formula_dependencies_and_virtualenv_target() -> None:
    """Verify render_formula includes python-tk dependency and targets virtualenv libexec/bin/python."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from scripts.publish_homebrew import render_formula

    formula_str = render_formula("0.7.0", "dummy_sha256")
    assert 'depends_on "python@3.14"' in formula_str
    assert 'depends_on "python-tk@3.14"' in formula_str
    assert 'libexec/"bin/python"' in formula_str
    assert "import tkinter; import clownfish" in formula_str
