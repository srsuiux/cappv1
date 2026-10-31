"""Check that a release tag matches the package version, without running any project code.

    check_release_tag.py v1.7.0     exit 0 if src/cappv1/version.py says 1.7.0, else exit 1 with a message
    check_release_tag.py --print    print the version
"""

import re
import sys
from pathlib import Path

VERSION_FILE = Path(__file__).resolve().parents[2] / "src" / "cappv1" / "version.py"
PATTERN = re.compile(r'^VERSION\s*=\s*"(\d+\.\d+\.\d+)"\s*$', re.MULTILINE)


def read_version() -> str:
    match = PATTERN.search(VERSION_FILE.read_text(encoding="utf-8"))
    if not match:
        sys.exit(f'{VERSION_FILE} has no line like VERSION = "1.2.3"; cannot read the package version.')
    return match.group(1)


def main(argv: list[str]) -> int:
    if argv == ["--print"]:
        print(read_version())
        return 0
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    version = read_version()
    if argv[0] != f"v{version}":
        print(f"Tag {argv[0]} does not match the package version {version} (expected v{version}).", file=sys.stderr)
        return 1
    print(f"Tag {argv[0]} matches version {version}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
