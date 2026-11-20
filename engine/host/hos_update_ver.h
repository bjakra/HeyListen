/* (hookshot) What the update offer and the setup's --play both need, in one place (host/hos_update.c, builder/setup/setup.c):
   which release tags may be shown and passed on, which of two versions is newer, and the options file's update_check line. */
#ifndef HOS_UPDATE_VER_H
#define HOS_UPDATE_VER_H
#include <ctype.h>
#include <string.h>

/* a release tag as it may be shown and passed on to the Builder: letters, digits and . _ + - (from the network, or a
   file of the game folder) */
static inline int safe_tag(const char *s) {
    size_t n = strlen(s);
    if (!n || n > 80) return 0;
    for (size_t i = 0; i < n; i++)
        if (!isalnum((unsigned char)s[i]) && !strchr("._+-", s[i])) return 0;
    return 1;
}

/* a version to order, as builder/linux/linux_update.py release_key: a release tag (v0.3.2, v0.4.0-rc.1) or git describe's
   v0.3.2-435-g1a2b3c4[-dirty], what a build from the Actions tab or a checkout carries: after v0.3.2, before any later release.
   (issue 14: such a build, ahead of the release, was told the release was a new version.) 0: it names no release (dev, a bare
   commit) */
typedef struct { unsigned long num[8]; int count, release, after; } ver_key;

/* (-N-g<hex>)?(-dirty)? up to the end: 1 after a tag, 0 nothing, -1 something else */
static inline int ver_tail(const char *p) {
    int after = 0;
    if (p[0] == '-' && isdigit((unsigned char)p[1])) {
        const char *q = p + 1;
        while (isdigit((unsigned char)*q)) q++;
        if (q[0] == '-' && q[1] == 'g' && q[2] && strchr("0123456789abcdef", q[2])) {
            for (q += 2; *q && strchr("0123456789abcdef", *q); q++) {}
            p = q, after = 1;
        }
    }
    if (!strcmp(p, "-dirty")) return 1;
    return *p ? -1 : after;
}

static inline int ver_parse(const char *s, ver_key *k) {
    memset(k, 0, sizeof *k);
    if (*s == 'v') s++;
    else if (!isdigit((unsigned char)*s) || !strchr(s, '.')) return 0;   /* (no v: digits and a dot, not a bare commit) */
    for (;;) {
        int digits = 0;
        unsigned long n = 0;
        for (; isdigit((unsigned char)*s); s++)
            if (++digits > 9) return 0;
            else n = n * 10 + (unsigned long)(*s - '0');
        if (!digits || k->count == 8) return 0;
        k->num[k->count++] = n;
        if (*s != '.') break;
        s++;
    }
    int t = ver_tail(s);
    k->release = 1;
    if (t < 0) {   /* -rc.1: a prerelease, before its release; its name is not ordered (latest never names one) */
        const char *q = s + 1;
        while (isdigit((unsigned char)*q)) q++;
        if (*s != '-' || (q[0] == '-' && q[1] == 'g')) return 0;
        for (s++;;) {
            if (!isalnum((unsigned char)*s)) return 0;
            while (isalnum((unsigned char)*s)) s++;
            if (*s != '.') break;
            s++;
        }
        if ((t = ver_tail(s)) < 0) return 0;
        k->release = 0;
    }
    k->after = t;
    return 1;
}

/* whether the latest release is newer than the folder's version. When either names no release, it is offered when the
   two differ, as before */
static inline int ver_newer(const char *tag, const char *have) {
    ver_key a, b;
    if (!ver_parse(tag, &a) || !ver_parse(have, &b)) return strcmp(tag, have) != 0;
    for (int i = 0; i < a.count || i < b.count; i++) {   /* (v1.0 before v1.0.0, as Python orders tuples) */
        if (i == a.count || i == b.count) return i == b.count;
        if (a.num[i] != b.num[i]) return a.num[i] > b.num[i];
    }
    if (a.release != b.release) return a.release;
    return a.after > b.after;
}
/* hookshot_options.ini's update_check line, the one the menu's "Check for updates" row keeps (1 the default, 0 off; the last line
   counts). "Don't ask again" in the offer writes the same line, so the row and the offer agree. 1 when the offer is turned off */
static inline int ini_update_off(const char *ini) {
    int off = 0;
    for (const char *p = ini; p && *p; p = strchr(p, '\n'), p = p ? p + 1 : NULL) {
        while (*p == ' ' || *p == '\t') p++;
        if (strncmp(p, "update_check=", 13)) continue;
        const char *q = p + 13;
        while (*q == ' ' || *q == '\t') q++;
        off = *q == '0' && (q[1] == 0 || q[1] == '\n' || q[1] == '\r' || q[1] == ' ' || q[1] == '\t');
    }
    return off;
}

/* the options file with its update_check lines replaced by update_check=<0 or 1> at the end, every other line as it was. 0 when
   it does not fit in cap */
static inline int ini_with_update_check(const char *ini, int on, char *out, size_t cap) {
    size_t n = 0;
    for (const char *p = ini; p && *p;) {
        const char *e = strchr(p, '\n');
        const size_t len = e ? (size_t)(e - p) + 1 : strlen(p);
        const char *q = p;
        while (*q == ' ' || *q == '\t') q++;
        if (strncmp(q, "update_check=", 13)) {
            if (n + len + 2 >= cap) return 0;
            memcpy(out + n, p, len), n += len;
            if (!e) out[n++] = '\n';
        }
        p += len;
    }
    if (n + 16 > cap) return 0;
    memcpy(out + n, on ? "update_check=1\n" : "update_check=0\n", 16);   /* (15 characters and the end) */
    return 1;
}

#endif
