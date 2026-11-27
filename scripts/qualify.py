"""Qualify exact installed wheel and sdist behavior with the syntax extra."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


def main():
    directory = Path(sys.argv[1]).resolve()
    artifacts = sorted([*directory.glob("*.whl"), *directory.glob("*.tar.gz")])
    if len(artifacts) != 2:
        raise ValueError("Select exactly one wheel and one source distribution")
    for artifact in artifacts:
        with TemporaryDirectory() as temporary:
            outside = Path(temporary)
            environment = outside / "environment"
            subprocess.run(["uv", "venv", str(environment), "--python", sys.executable], check=True)
            python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            subprocess.run(
                ["uv", "pip", "install", "--python", str(python), str(artifact) + "[syntax,dev]"],
                cwd=outside,
                check=True,
            )
            probe = "import clownfish; from pathlib import Path; import sys; from importlib.metadata import version; assert Path(clownfish.__file__).is_relative_to(Path(sys.prefix)); assert version('clownfish') == clownfish.__version__ == '0.7.0'; assert version('escape-colors') == '0.3.0'"
            subprocess.run([str(python), "-I", "-c", probe], cwd=outside, check=True)
            configuration = outside / "pytest.ini"
            configuration.write_text("[pytest]\n")
            subprocess.run(
                [
                    str(python),
                    "-I",
                    "-m",
                    "pytest",
                    "-c",
                    str(configuration),
                    "--import-mode=importlib",
                    str(ROOT / "tests"),
                    "-q",
                ],
                cwd=outside,
                check=True,
            )
            subprocess.run(["uv", "pip", "check", "--python", str(python)], cwd=outside, check=True)
            print(
                json.dumps(
                    {
                        "artifact": artifact.name,
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                        "profile": "published-syntax/1",
                    }
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()
