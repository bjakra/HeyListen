#include "hos.h"
#include <stdlib.h>
#include <string.h>

/* (HeyListen better-aa) The sdk's memory and string functions as host code. They ran as lifted guest code: memcpy
   (0x8572f020) is a one-instruction veneer to a PLT stub whose GOT holds __memcpy_aarch64, so each of the 300 M calls
   the PGO training run counted went through an indirect jump and then the AArch64 optimised-routines copy, lifted, with
   a page mark per guest store and a poll in each loop. HLE() hooks each at its definition (and where a module imports
   it); __memcpy_aarch64(_simd) too, for the sdk's own direct calls. Exact: memmove for the copies (the AArch64 routines
   allow overlap), the pages marked written after the bytes as a guest store marks them (hos_mark_written), x0 kept
   (the destination, as they return it). These were TOTK's entry hooks (ENTRY_HOOK_SYM), which nothing here splices in.
   RX_GUEST_LIBC=1 at the lift leaves them lifted (nx2/standalone.py). */

#if defined(RX_WEB_MT) && RX_WEB_MT
void rx_wait_writebacks_reading(const void *p, uint64_t n);   /* gpu/render/rx_nvn.h */
#define WAIT_WRITEBACKS(p, n) rx_wait_writebacks_reading(p, n)
#else
#define WAIT_WRITEBACKS(p, n) ((void)0)
#endif

static inline void libc_copy(Ctx *c) {
    const uint64_t n = ARG(2);
    if (n) {
        WAIT_WRITEBACKS(GP(ARG(1)), n);   /* (TOTK copies some rendered maps with the CPU) */
        memmove(GP(ARG(0)), GP(ARG(1)), (size_t)n);
        HOS_WRITTEN(GP(ARG(0)), (size_t)n);
    }
}

static inline void libc_compare(Ctx *c) {
    const uint8_t *a = (const uint8_t *)GP(ARG(0)), *b = (const uint8_t *)GP(ARG(1));
    const size_t n = (size_t)ARG(2);
    int r = 0;
    if (n && memcmp(a, b, n)) {
        size_t i = 0;
        while (a[i] == b[i]) i++;
        r = (int)a[i] - (int)b[i];
    }
    RET((uint64_t)(int64_t)r);
}

HLE(memcpy) { libc_copy(c); }
HLE(__memcpy_aarch64) { libc_copy(c); }
HLE(__memcpy_aarch64_simd) { libc_copy(c); }
HLE(memmove) { libc_copy(c); }

HLE(memset) {
    const uint64_t n = ARG(2);
    if (n) {
        memset(GP(ARG(0)), (int)(uint8_t)ARG(1), (size_t)n);
        HOS_WRITTEN(GP(ARG(0)), (size_t)n);
    }
}

HLE(memcmp) { libc_compare(c); }
HLE(bcmp) { libc_compare(c); }

HLE(strlen) { RET(strlen((const char *)GP(ARG(0)))); }

HLE(strcmp) {
    const uint8_t *a = (const uint8_t *)GP(ARG(0)), *b = (const uint8_t *)GP(ARG(1));
    int r = 0;
    if (strcmp((const char *)a, (const char *)b)) {
        size_t i = 0;
        while (a[i] && a[i] == b[i]) i++;
        r = (int)a[i] - (int)b[i];
    }
    RET((uint64_t)(int64_t)r);
}
