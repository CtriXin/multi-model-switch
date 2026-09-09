#!/usr/bin/env python3
"""Build the checked-in Web bundle so end users need no frontend toolchain."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps/mms-web"
TARGET = ROOT / "mms_web_static"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-install", action="store_true", help="Use existing development node_modules")
    args = parser.parse_args()
    if not args.skip_install:
        subprocess.run(["npm", "ci", "--workspaces=false", "--ignore-scripts"], cwd=APP, check=True)
    with tempfile.TemporaryDirectory(prefix="dist-package-", dir=APP) as temporary:
        subprocess.run(["npm", "run", "build", "--workspaces=false", "--", "--outDir", temporary], cwd=APP, check=True)
        source_hash = hashlib.sha256()
        inputs = [*sorted((APP / "src").rglob("*")), APP / "package.json", APP / "package-lock.json", APP / "index.html", APP / "vite.config.ts", APP / "tsconfig.json"]
        for path in inputs:
            if path.is_file():
                source_hash.update(path.relative_to(APP).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
        files = {p.relative_to(temporary).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(Path(temporary).rglob("*")) if p.is_file()}
        manifest = {"version": json.loads((APP / "package.json").read_text())["version"],
                    "sourceSha256": source_hash.hexdigest(), "files": files}
        Path(temporary, "build.json").write_text(json.dumps(manifest, indent=2) + "\n")
        # This directory contains generated release assets only.
        if TARGET.exists():
            shutil.rmtree(TARGET)
        shutil.copytree(temporary, TARGET)
    print(f"Packaged MMS Pilot {manifest['version']} -> {TARGET}")


if __name__ == "__main__":
    main()
