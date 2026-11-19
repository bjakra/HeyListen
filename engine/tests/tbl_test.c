/* (HeyListen better-aa) TBL / TBX as the lifter emits them (tbl_lifted.h, by tests/test_tbl.py) against the rule
   written out here from the Arm ARM: the table the regs registers from rn on (wrapping at v31), each byte of rm an index;
   an index past the table gives 0 (TBL) or keeps rd's byte (TBX); the .8B forms zero rd's upper half.

   tbl_test <n> <seed>   n random register files per guest word (indices biased into the table and its edges)
   Exit 0: no mismatch; 1: a mismatch. */
#include "a64.h"
#include <stdio.h>
#include <stdlib.h>

#include "tbl_lifted.h"

static uint64_t rs;
static uint64_t rnd(void) { rs ^= rs << 13; rs ^= rs >> 7; rs ^= rs << 17; return rs; }

static void reference(uint64_t v[32][2], unsigned w) {
    const unsigned q = (w >> 30) & 1, rm = (w >> 16) & 31, rn = (w >> 5) & 31, rd = w & 31;
    const unsigned regs = ((w >> 13) & 3) + 1, tbx = (w >> 12) & 1;
    uint8_t t[64], x[16], d[16], r[16];
    for (unsigned k = 0; k < regs; k++) memcpy(t + 16 * k, v[(rn + k) % 32], 16);
    memcpy(x, v[rm], 16);
    memcpy(d, v[rd], 16);
    for (unsigned i = 0; i < 16; i++) {
        if (i >= (q ? 16u : 8u)) r[i] = 0;
        else if (x[i] < 16 * regs) r[i] = t[x[i]];
        else r[i] = tbx ? d[i] : 0;
    }
    memcpy(v[rd], r, 16);
}

int main(int argc, char** argv) {
    const long n = argc > 1 ? atol(argv[1]) : 100000;
    rs = argc > 2 ? strtoull(argv[2], 0, 10) : 1;
    long bad = 0;
    static Ctx c, want;
    for (unsigned g = 0; g < sizeof GUEST / sizeof GUEST[0]; g++)
        for (long it = 0; it < n; it++) {
            for (int r = 0; r < 32; r++) {
                uint8_t b[16];
                const unsigned kind = (unsigned)(rnd() % 4);
                for (int i = 0; i < 16; i++) {
                    const unsigned v = (unsigned)rnd();
                    b[i] = kind == 0 ? (uint8_t)v : kind == 1 ? (uint8_t)(v % 80) : kind == 2 ? (uint8_t)(15 + 16 * (v % 5) + (v >> 8) % 2)
                                                                                   : (uint8_t)(v % 2 ? 0xff - v % 3 : 0x80 + v % 3);
                }
                memcpy(c.vreg[r], b, 16);
            }
            want = c;
            reference(want.vreg, GUEST[g].word);
            for (int form = 0; form < 2; form++) {
                Ctx got = c;
                (form ? GUEST[g].hot : GUEST[g].lifted)(&got);
                if (memcmp(got.vreg, want.vreg, sizeof got.vreg)) {
                    if (bad++ < 10) printf("MISMATCH %s (%s form), run %ld\n", GUEST[g].name, form ? "hot" : "lifted", it);
                }
            }
        }
    printf("tbl: %u guest words x %ld runs, %ld mismatches (%s)\n", (unsigned)(sizeof GUEST / sizeof GUEST[0]), n, bad,
#if defined(__SSE4_1__)
           "SSE4.1: pshufb");
#else
           "the byte loop");
#endif
    return bad ? 1 : 0;
}
