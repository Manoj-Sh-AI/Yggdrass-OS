"""Install a pinned official local Temporal CLI after verifying its release checksum."""

import argparse
import hashlib
import io
import json
import os
import platform
import tarfile
import zipfile
from pathlib import Path
from urllib.request import urlopen

VERSION = "1.10.1"
ASSETS = {
    ("Windows", "amd64"): (
        "windows_amd64.zip",
        "5069cdb76569914305ed7c90e1c8406cd27bcb6c2a822fce201a488c34ab074f",
    ),
    ("Linux", "amd64"): (
        "linux_amd64.tar.gz",
        "4c1500e2ce2d4de136e5fe8852d9b7f82eb62f19b6b383b3e0c040519a9d20b1",
    ),
}


def install(directory):
    architecture = (
        "amd64" if platform.machine().lower() in ("amd64", "x86_64") else platform.machine().lower()
    )
    suffix, checksum = ASSETS[(platform.system(), architecture)]
    url = f"https://github.com/temporalio/cli/releases/download/v{VERSION}/temporal_cli_{VERSION}_{suffix}"
    with urlopen(url, timeout=120) as response:
        raw = response.read(200_000_001)
    if len(raw) > 200_000_000 or hashlib.sha256(raw).hexdigest() != checksum:
        raise RuntimeError("The official Temporal archive failed verification.")
    name = "temporal.exe" if os.name == "nt" else "temporal"
    if suffix.endswith("zip"):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = [p for p in archive.namelist() if Path(p).name == name]
            if len(members) != 1:
                raise RuntimeError("Unexpected Temporal archive layout.")
            executable = archive.read(members[0])
    else:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
            members = [p for p in archive.getmembers() if Path(p.name).name == name and p.isfile()]
            if len(members) != 1:
                raise RuntimeError("Unexpected Temporal archive layout.")
            with archive.extractfile(members[0]) as stream:
                executable = stream.read()
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    if target.exists() and target.read_bytes() != executable:
        raise RuntimeError("An existing different Temporal binary will not be overwritten.")
    target.write_bytes(executable)
    target.chmod(0o700)
    return {
        "version": VERSION,
        "binary": str(target),
        "sha256": hashlib.sha256(executable).hexdigest(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(install(args.directory)))
