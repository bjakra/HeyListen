"""The eight-note Scarecrow melody keeps its recorded rhythm across frame-rate caps (after upstream Hookshot 2d8044fb, Longshot
08771847, Hookshot #2906 and #2828, Longshot #87 and #294).

Playback (f_832b32b0), the eight-note recording (f_832b6840, mode 10) and its completion (f_832b2690) add the frame step cut to
whole frames to one elapsed counter (+0x265fc of the actor): advancing the saved note delays, timing the notes and gaps, writing
the eighth note's length. Above a 60 cap the step is under 1 and the cut is 0 every frame: playback stayed on its first note, and
a recording lost the rhythm (every length 0), the eighth note too (the last length is written at completion). In this tree the
three are lift hooks (host/hl_step.c HL_WHOLE_HOOK, the cuts unsigned: "u"; f_832b6840 has another unsigned cut, the other
recording mode's, added to x12, that stays: "u10", the one before the addition to x10), nx2/hl_gates.py puts a line after each cut
making the count hos_frame_whole(the counter's address, the step, the game's count): one remainder shared by the three.

Authored lifted functions of the real shapes are hooked by the real hl_gates with the hooks host/hl_step.c asks for, then compiled
with the host's hos_frame_whole. Record note holds and gaps at 60, 120 and 240 updates per second and play every recording at
each rate; the counter's reset between events keeps its remainder; the other recording mode's cut and the signed cuts stay the
game's; a second run changes nothing; the unhooked functions fail the same checks. No game data, save, audio or GPU is needed.

python -I -B tests/test_scarecrow_timing.py [--cc gcc]
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cc", "gcc"]

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nx2"))
import hl_gates  # noqa: E402

HOST_ANCHOR = "uint32_t hos_frame_whole(uint64_t at, uint32_t amount_bits, uint32_t game) {"
ADDRS = ("832b6840", "832b32b0", "832b2690")

CUT = hl_gates.CUT % 8
UCUT = CUT.replace(",32,32,1,3,", ",32,32,0,3,")
ADD = hl_gates.WHOLE_ADD

LIFTED = ('#include "a64.h"\n'
          + hl_gates.HEAD % "832b6840" + '    if (c->x[2]) {\n' + UCUT + ADD % 12
          + '    } else {\n' + UCUT + ADD % 10 + '    }\n    c->counter = (uint32_t)c->x[8];\n}\n'
          + hl_gates.HEAD % "832b32b0" + CUT + "    c->other = (uint32_t)c->x[8];\n" + UCUT + "    c->counter += (uint32_t)c->x[8];\n}\n"
          + hl_gates.HEAD % "832b2690" + UCUT + "    c->counter += (uint32_t)c->x[8];\n}\n")

FIXTURE = r'''#define _CRT_SECURE_NO_WARNINGS
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "frame_whole.h"
typedef int SRWLOCK;
#define SRWLOCK_INIT 0
static void AcquireSRWLockExclusive(SRWLOCK *l) { *l = 1; }
static void ReleaseSRWLockExclusive(SRWLOCK *l) { *l = 0; }
volatile uint32_t hos_frame_seconds_bits;
@HOST@
#define A64_NOESC
typedef struct { uint64_t x[32], vreg[32][2]; uint32_t fpcr, fpsr, counter, other; } Ctx;
/* (exact for this fixture's finite, nonnegative frame steps) */
static uint64_t recomp_fp_to_int(uint64_t b, int iw, int ow, int s, int mode, uint32_t fpcr, uint32_t *fpsr) {
    (void)iw, (void)ow, (void)s, (void)mode, (void)fpcr, (void)fpsr;
    float f;
    const uint32_t low = (uint32_t)b;
    memcpy(&f, &low, 4);
    return (uint32_t)(f != f ? 0 : (int32_t)f);
}
@LIFTED@
static const uint64_t sc_object = 0x100000, sc_counter = 0x1265fc;
static int failures;
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); ++failures; } } while (0)
static uint32_t bits(float f) { uint32_t b; memcpy(&b, &f, 4); return b; }
/* one update of a site; 0 playback, 1 recording, 2 completion */
static void tick(Ctx *c, int rate, int site) {
    hos_frame_seconds_bits = rate > 60 ? bits(1.0f / rate) : 0;
    c->vreg[0][0] = bits(60.0f / rate);
    c->x[19] = sc_object;
    c->x[9] = sc_counter;
    c->x[10] = c->counter;
    c->x[2] = 0;
    if (site == 2) f_832b2690(c);
    else if (site) f_832b6840(c);
    else f_832b32b0(c);
}
int main(void) {
    const int rates[] = {60, 120, 240};
    for (unsigned r = 0; r < 3; ++r) {
        for (unsigned p = 0; p < 3; ++p) {
            Ctx c = {0};
            uint32_t melody = 0;
            const int before = failures;
            /* Eight 0.1-second holds and seven 0.4-second gaps; completion times the eighth hold. */
            for (int event = 0; event < 15; ++event) {
                const int expected = event % 2 ? 24 : 6;
                c.counter = 0;
                for (int f = 0; f < expected * rates[r] / 60; ++f) tick(&c, rates[r], event == 14 ? 2 : 1);
                CHECK(c.counter == (uint32_t)expected);
                melody += c.counter;
            }
            CHECK(melody == 216);
            c.counter = 0;
            int frames = 0;
            while (c.counter < melody && frames < rates[p] * 10) { tick(&c, rates[p], 0); ++frames; }
            CHECK(c.counter == 216);
            CHECK(frames == 216 * rates[p] / 60);
            printf("record %d, play %d: %s (stored %u ticks, playback %d updates)\n", rates[r], rates[p],
                   before == failures ? "PASS" : "FAIL", melody, frames);
        }
    }
    /* a sub-tick remainder survives a counter reset and is shared by the three sites */
    Ctx s = {0};
    tick(&s, 240, 1);
    CHECK(s.counter == 0);
    s.counter = 0;
    tick(&s, 240, 2);
    CHECK(s.counter == 0);
    tick(&s, 240, 0);
    CHECK(s.counter == 0);
    tick(&s, 240, 2);
    CHECK(s.counter == 1);
    /* the other recording mode's cut (added to x12) and the playback function's signed cut are the game's own */
    Ctx o = {0};
    hos_frame_seconds_bits = bits(1.0f / 240);
    o.x[2] = 1; o.x[12] = 7; o.x[19] = sc_object; o.x[9] = sc_counter;
    o.vreg[0][0] = bits(0.25f);
    f_832b6840(&o);
    CHECK(o.counter == 7);
    if (!failures) puts("PASS: short-song recording and playback share a fractional clock");
    return failures != 0;
}
'''


def check(cond, what):
    if not cond:
        raise SystemExit("FAIL: " + what)


def block(source, marker):
    check(marker in source, "host/hl_step.c has no '%s'" % marker)
    start = source.index(marker)
    return source[start:start + re.search(r"^}", source[start:], re.M).end()]


def hooked_text():
    """LIFTED with the hooks host/hl_step.c asks for put in by the real hl_gates, and the checks of the put-in"""
    asked = {a: v for a, v in hl_gates.wanted_lifts().items() if a in ADDRS}
    check(sorted(asked) == sorted(ADDRS), "host/hl_step.c does not ask for all three Scarecrow's Song hooks: %s" % sorted(asked))
    check(asked["832b6840"][2][2] == "u10" and asked["832b32b0"][2][2] == "u" and asked["832b2690"][2][2] == "u",
          "the hooks' unsigned modes are not u10 / u / u")
    check(asked["832b32b0"][2][1] == asked["832b2690"][2][1], "playback and completion keep different remainders")
    hashes = {a: hl_gates.text_hash(LIFTED, a) for a in ADDRS}
    with tempfile.TemporaryDirectory(prefix="scarecrow-hook-") as tmp:
        gen, host = Path(tmp) / "gen", Path(tmp) / "host"
        gen.mkdir()
        host.mkdir()
        code = gen / "code_000.c"
        code.write_text(LIFTED, encoding="utf-8", newline="")
        (host / "hl_w.c").write_text("".join('HL_WHOLE_HOOK(%s, "%s", %d, "%s", "%s");\n' % (a, hashes[a], *asked[a][2])
                                             for a in ADDRS), encoding="utf-8")
        hl_gates.apply(str(gen), str(host), quiet=True)
        s = code.read_text(encoding="utf-8")
        check(s.count("= hos_frame_whole(") == 3, "not one hook in each of the three functions (the other cut of f_832b6840, "
              "or a signed cut, hooked)")
        for a in ADDRS:
            check(hl_gates.text_hash(s, a) == hashes[a], "the hook changed f_%s's hash" % a)
        check(UCUT + hl_gates.lift_lines("whole", "832b6840", asked["832b6840"][2])[0] + ADD % 10 in s,
              "f_832b6840's hook is not between the cut and the addition to x10")
        check(UCUT + ADD % 12 in s, "the other recording mode's cut was changed")
        check(CUT + "    c->other" in s, "the playback function's signed cut was changed")
        hl_gates.apply(str(gen), str(host), quiet=True)
        check(code.read_text(encoding="utf-8") == s, "a second run changed a hooked file")
        old = re.compile(r"^.*/\* hl gate ([0-9a-f]{8}) \*/\n", re.M).sub("", s)
        check(old == LIFTED, "an older tree's gates script does not restore the lift")
    return s


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cc", default="gcc")
    a = p.parse_args()
    hooked = hooked_text().replace('#include "a64.h"\n', "")
    step = (ROOT / "host" / "hl_step.c").read_text(encoding="utf-8")
    fixture = FIXTURE.replace("@HOST@", block(step, HOST_ANCHOR))
    with tempfile.TemporaryDirectory(prefix="scarecrow-") as tmp:
        c, exe = Path(tmp) / "fixture.c", Path(tmp) / "fixture.exe"
        cmd = [a.cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", "-Wno-unused-parameter",
               "-I", str(ROOT / "host"), str(c), "-o", str(exe), "-lm"]
        c.write_text(fixture.replace("@LIFTED@", hooked), encoding="utf-8")
        subprocess.run(cmd, check=True)
        subprocess.run([str(exe)], check=True, timeout=30)
        # (the negative control: the game's own cut fails the same checks above 60 fps)
        c.write_text(fixture.replace("@LIFTED@", LIFTED.replace('#include "a64.h"\n', "")), encoding="utf-8")
        subprocess.run(cmd, check=True)
        r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
        check(r.returncode != 0 and "FAIL" in r.stdout, "the unhooked functions pass the checks: they prove nothing")
    print("scarecrow timing: ok")


if __name__ == "__main__":
    main()
