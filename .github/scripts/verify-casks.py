"""Check generated casks as text; releases and asset digests come from GitHub."""

import json
import re
import sys
from pathlib import Path

RELEASE_URL = "https://github.com/spacelift-solutions/liftoff/releases/download"
TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-rc\.([1-9][0-9]*))?")


def latest(releases, candidate):
    versions = {}
    for release in releases:
        match = TAG.fullmatch(release["tag_name"])
        if not match or release["draft"] or release["prerelease"] != candidate:
            continue
        if bool(match[4]) == candidate:
            versions[tuple(int(n) for n in match.groups() if n is not None)] = release
    if not versions:
        raise ValueError("no published release found for the selected channel")
    return versions[max(versions)]


def verify(path, releases):
    release = latest(releases, path.stem == "liftoff-rc")
    version = release["tag_name"][1:]
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{path}: expected a regular cask file")
    source = path.read_text()
    if re.findall(r"^[ \t]*version\b.*$", source, re.M) != [f'  version "{version}"']:
        raise ValueError(f"{path}: expected version {version} from the latest published release")
    assets = {asset["name"]: asset for asset in release["assets"]}

    for block, os_name in (("macos", "darwin"), ("linux", "linux")):
        sections = re.findall(rf"^  on_{block} do\n((?:^    .*\n)+)^  end$", source, re.M)
        if len(sections) != 1:
            raise ValueError(f"{path}: expected one generated on_{block} block")
        for cpu, arch in (("intel", "amd64"), ("arm", "arm64")):
            suffix = f"{os_name}_{arch}.tar.gz"
            archive = f"liftoff_{version}_{suffix}"
            asset = assets.get(archive, {})
            digest = asset.get("digest") or ""
            if asset.get("state") != "uploaded" or not asset.get("size") or not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
                raise ValueError(f"{path}: release {version} lacks a complete archive and SHA-256 for {archive}")
            url = RELEASE_URL + "/v#{version}/liftoff_#{version}_" + suffix
            stanza = f'    on_{cpu} do\n      sha256 "{digest[7:]}"\n      url "{url}"\n    end\n'
            if sections[0].count(stanza) != 1:
                raise ValueError(f"{path}: {block}/{cpu} must use {archive} and its published SHA-256")
    if len(re.findall(r"^[ \t]*(?:sha256|url)\b", source, re.M)) != 8:
        raise ValueError(f"{path}: unexpected download directives outside the four generated platform entries")
    print(f"{path}: verified {version} and all four platform downloads")


if __name__ == "__main__":
    releases = [release for page in json.load(sys.stdin) for release in page]
    try:
        for argument in sys.argv[1:]:
            verify(Path(argument), releases)
    except ValueError as error:
        sys.exit(str(error))
