"""The game's update offer (host/hos_update.c) names only a newer release: not the one a development build is ahead of
(issue 14), and in the order builder/linux/linux_update.py release_key gives. The shared part of the file is compiled as it
is, both platform halves are checked to use it.

python -I -B tests/test_update_order.py [--cc gcc]
"""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "host" / "hos_update.c"
HEADER = ROOT / "host" / "hos_update_ver.h"
sys.path.insert(0, str(ROOT / "builder" / "linux"))
import linux_update  # noqa: E402

MAIN = r"""
#include <stdio.h>
int main(int argc, char **argv) {
    (void)safe_tag;
    (void)ini_update_off;
    (void)ini_with_update_check;
    for (int i = 1; i + 1 < argc; i += 2) printf("%d\n", ver_newer(argv[i], argv[i + 1]));
    return 0;
}
"""

# (latest release, the folder's version, offered)
CASES = [
    ("v0.3.2", "v0.3.2", 0),                         # equal
    ("v0.3.2", "v0.3.1", 1),                         # an older folder
    ("v0.3.1", "v0.3.2", 0),                         # a newer folder
    ("v0.3.2", "v0.3.2-435-g1a2b3c4", 0),            # issue 14: a development build ahead of the release
    ("v0.3.2", "v0.3.2-435-g1a2b3c4-dirty", 0),
    ("v0.3.2", "v0.3.2-dirty", 0),
    ("v0.3.3", "v0.3.2-435-g1a2b3c4", 1),            # ... and behind the next one
    ("v0.4.0", "v0.3.2-3-gabcdef0", 1),
    ("v0.10.0", "v0.9.9", 1),                        # components are numbers, not text
    ("v0.9.9", "v0.10.0", 0),
    ("v1.0.0", "v0.99.99", 1),
    ("v0.3.2", "v0.3.2-rc.1", 1),                    # a prerelease is before its release
    ("v0.3.2", "v0.3.2-rc2", 1),
    ("v0.3.2-rc2", "v0.3.2", 0),
    ("v0.3.2-rc.2", "v0.3.2-rc.1", 0),               # (prerelease names are not ordered, as release_key)
    ("v0.3.2", "v0.3.2-rc.1-2-gabc1234", 1),
    ("v0.3.2", "v0.0.0-1a2b3c4", 1),                 # the Windows builder workflow with no tag (a prerelease of 0.0.0)
    ("v1.0", "v1.0.0", 0),                           # (shorter first, as Python orders tuples)
    ("v1.0.0", "v1.0", 1),
    ("v0.3.2", "0.3.2", 0),                          # no v: digits and a dot
    # names no release: offered when different, as before
    ("v0.3.2", "dev", 1),
    ("v0.3.2", "1a2b3c4", 1),
    ("v0.3.2", "1234567", 1),
    ("dev", "dev", 0),
    ("release-7", "v0.3.2", 1),
    ("v0.3.2", "v0.3.2-435-gXYZ", 1),
    ("v0.3.2", "v0.3.2-", 1),
    ("v0.3.2", "v0.3.2-rc..1", 1),
    ("v0.3.2", "v", 1),
]
# (beyond what the C keeps, more than 8 parts or 10 digits: there it names no release, unlike in Python)
LIMITS = [
    ("v0.3.2", "v1.2.3.4.5.6.7.8.9", 1),
    ("v0.3.2", "v0.3.9999999999", 1),
]


def reference(tag, have):
    """release_key's order (builder/linux/linux_update.py), and different-is-newer when either names no release"""
    a, b = linux_update.release_key(tag), linux_update.release_key(have)
    return int(a > b) if a and b else int(tag != have)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", default="gcc")
    args = parser.parse_args()
    text = SOURCE.read_text(encoding="utf-8")
    shared = HEADER.read_text(encoding="utf-8")   # (host/hos_update_ver.h: what the offer and the setup share)
    assert '#include "hos_update_ver.h"' in text
    for tag in ("ver_newer(", "ver_parse(", "ver_tail("):
        assert tag in shared, "%s is not in host/hos_update_ver.h" % tag
    # both halves ask ver_newer, not whether the two strings differ
    assert text.count("if (!ver_newer(tag, have) || !strcmp(tag, skipped)) return;") == 2
    assert "!strcmp(tag, have)" not in text
    with tempfile.TemporaryDirectory(prefix="hookshot-update-order-") as temp:
        source, executable = Path(temp) / "fixture.c", Path(temp) / "fixture.exe"
        source.write_text(shared + MAIN, encoding="utf-8")
        priority = {"creationflags": getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)}
        subprocess.run([args.cc, "-std=c11", "-O0", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(executable)],
                       check=True, **priority)
        pairs = [s for tag, have, _ in CASES + LIMITS for s in (tag, have)]
        got = subprocess.run([str(executable), *pairs], check=True, capture_output=True, text=True, **priority).stdout.split()
    failed = []
    for i, ((tag, have, want), out) in enumerate(zip(CASES + LIMITS, got)):
        if int(out) != want or (i < len(CASES) and reference(tag, have) != want):
            failed.append("latest %s, folder %s: hos_update.c %s, release_key %d, expected %d" % (tag, have, out, reference(tag, have), want))
    assert len(got) == len(CASES + LIMITS), got
    if failed:
        sys.exit("\n".join(failed))
    print("%d cases agree with release_key, %d beyond the C limits" % (len(CASES), len(LIMITS)))


if __name__ == "__main__":
    main()
