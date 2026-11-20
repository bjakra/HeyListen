"""The game's update offer (host/hos_update.c) is on for a game the player started, off when the launcher or the builder started it,
and the player can turn it off for good: "Never ask again" in the offer and the menu's Settings row "Check for updates" both keep
update_check=0 in hookshot_options.ini. The two helpers for that line are compiled as they are; the rest is checked in the source.

python -I -B tests/test_update_offer.py [--cc gcc]
"""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "host" / "hos_update.c"
HEADER = ROOT / "host" / "hos_update_ver.h"
MENU = ROOT / "gpu" / "vk" / "vk_menu.cpp"
MENU_H = ROOT / "gpu" / "vk" / "vk_menu.h"

MAIN = r"""
#include <stdio.h>
int main(int argc, char **argv) {
    (void)safe_tag; (void)ver_newer;
    for (int i = 1; i < argc; i++) {
        char out[256], small[20];
        const int fits = ini_with_update_check(argv[i], 0, out, sizeof out);
        printf("%d %d %d ", ini_update_off(argv[i]), fits, ini_with_update_check(argv[i], 1, small, sizeof small));
        for (const char *p = out; fits && *p; p++) putchar(*p == '\n' ? '~' : *p);
        putchar('\n');
    }
    return 0;
}
"""

NL, CR = chr(10), chr(13)
# (the options file, whether its update_check line says off, the file as written for "never ask again")
CASES = [
    ("", 0, "update_check=0" + NL),
    ("fullscreen=1" + NL, 0, "fullscreen=1" + NL + "update_check=0" + NL),
    ("fullscreen=1", 0, "fullscreen=1" + NL + "update_check=0" + NL),                        # (no newline at the end)
    ("update_check=0" + NL, 1, "update_check=0" + NL),
    ("a=1" + NL + "update_check=0" + NL + "b=2" + NL, 1, "a=1" + NL + "b=2" + NL + "update_check=0" + NL),   # (once, at the end)
    ("update_check=1" + NL, 0, "update_check=0" + NL),
    ("update_check=0" + CR + NL, 1, "update_check=0" + NL),
    ("  update_check=0" + NL, 1, "update_check=0" + NL),
    ("update_check=0" + NL + "update_check=1" + NL, 0, "update_check=0" + NL),               # (the last line counts)
    ("update_check=1" + NL + "update_check=0" + NL, 1, "update_check=0" + NL),
    ("update_check=2" + NL, 0, "update_check=0" + NL),
    ("update_check=00" + NL, 0, "update_check=0" + NL),
    ("my_update_check=0" + NL, 0, "my_update_check=0" + NL + "update_check=0" + NL),         # (another key)
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", default="gcc")
    args = parser.parse_args()
    text = SOURCE.read_text(encoding="utf-8")
    shared = HEADER.read_text(encoding="utf-8")   # (host/hos_update_ver.h: what the offer and the setup share)
    for name in ("ini_update_off(", "ini_with_update_check("):
        assert name in shared, "%s is not in host/hos_update_ver.h" % name
    with tempfile.TemporaryDirectory(prefix="hookshot-update-offer-") as temp:
        source, executable = Path(temp) / "fixture.c", Path(temp) / "fixture.exe"
        source.write_text(shared + MAIN, encoding="utf-8")
        subprocess.run([args.cc, "-std=c11", "-O0", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(executable)], check=True)
        got = subprocess.run([str(executable), *[c[0] for c in CASES]], check=True, capture_output=True, text=True).stdout
    got = got.replace(CR, "")
    failed = []
    for (ini, off, written), line in zip(CASES, got.split(NL)):
        said, fits, small, out = line.split(" ", 3)
        if int(said) != off:
            failed.append("%r: update off said %s, expected %d" % (ini, said, off))
        if fits != "1" or out != written.replace(NL, "~"):
            failed.append("%r: wrote %r, expected %r" % (ini, out, written.replace(NL, "~")))
        if "update_check=" not in ini and len(ini) > 6 and small != "0":   # (a buffer too small for the file is refused, not cut)
            failed.append("%r: written into a buffer too small for it" % ini)
    assert len(got.split(NL)) == len(CASES) + 1, got
    if failed:
        sys.exit(NL.join(failed))

    # the offer is on by default, off for the launcher's start, and the player's choices are kept
    code = NL.join(l for l in text.splitlines() if not l.lstrip().startswith(("/*", "*", "//")))
    assert 'getenv("HOOKSHOT_UPDATE_CHECK")' not in code, "the offer must not need an opt-in any more"
    assert code.count('getenv("HOOKSHOT_NO_UPDATE_CHECK")') >= 2, "both platforms keep the launcher's way to turn it off"
    assert code.count("ini_update_off(") >= 2 and code.count("options_set_off(") >= 4, "both platforms read and write update_check="
    assert "WaitForSingleObject(t, UPDATE_WAIT_MS)" in code, "Windows never waits for the network without a limit"
    assert "--max-time 3" in code and "--retry" not in code, "Linux never waits long for curl"
    assert "Never ask again" in code and "never ask again" in code, "both offers have the choice"
    assert code.count("if (!ver_newer(tag, have) || !strcmp(tag, skipped)) return;") == 2
    # the menu row keeps the same line, on by default
    menu, header = MENU.read_text(encoding="utf-8"), MENU_H.read_text(encoding="utf-8")
    assert '{TAB_GAMEPLAY, "Check for updates", &opts.update_check, 0, 1, 1, tx_onoff,' in menu
    assert 'if (r.value == &opts.update_check) return "update_check";' in menu
    assert "int update_check = 1;" in header
    print("PASS: update offer: on by default, off for the launcher, update_check= kept by the offer and the menu row (%d cases)" % len(CASES))


if __name__ == "__main__":
    main()
