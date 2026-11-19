// (better-aa) RX_VK_TUNE: live switches for A/B tests (vk_tune.h).
#include "vk_tune.h"

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <mutex>
#include <string>
#include <sys/stat.h>

#include "vk_internal.h"   // (logf)

namespace mkwvk {

namespace {
struct Tune {
    std::mutex mu;
    std::map<std::string, int> values;
    int64_t next_look = 0;   // (steady clock, ms)
    time_t mtime = 0;
    off_t size = -1;
};
Tune& tune() {
    static Tune t;
    return t;
}
int64_t now_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
}
/// With t.mu held: the file read again when it changed since the last look
void refresh(Tune& t, const char* path) {
    const int64_t now = now_ms();
    if (now < t.next_look) return;
    t.next_look = now + 250;
    struct stat st {};
    if (stat(path, &st) != 0) {
        if (!t.values.empty()) t.values.clear(), logf("vk: tune: %s is gone: every switch as without it", path);
        t.mtime = 0, t.size = -1;
        return;
    }
    if (st.st_mtime == t.mtime && st.st_size == t.size) return;
    t.mtime = st.st_mtime, t.size = st.st_size;
    FILE* f = fopen(path, "rb");
    if (!f) return;
    std::map<std::string, int> read;
    char line[256];
    while (fgets(line, sizeof line, f)) {
        char* eq = strchr(line, '=');
        if (!eq || line[0] == '#') continue;
        *eq = 0;
        char* end = nullptr;
        const long v = strtol(eq + 1, &end, 10);
        if (end == eq + 1) continue;
        std::string key(line);
        while (!key.empty() && (key.back() == ' ' || key.back() == '\t')) key.pop_back();
        read[key] = (int)v;
    }
    fclose(f);
    if (read != t.values) {
        std::string said;
        for (const auto& [k, v] : read) said += " " + k + "=" + std::to_string(v);
        logf("vk: tune: %s:%s", path, said.empty() ? " (no switches)" : said.c_str());
    }
    t.values.swap(read);
}
}  // namespace

int tune_int(const char* key, int fallback) {
    static const char* const path = getenv("RX_VK_TUNE");
    if (!path || !*path) return fallback;
    Tune& t = tune();
    std::lock_guard lk(t.mu);
    refresh(t, path);
    const auto it = t.values.find(key);
    return it == t.values.end() ? fallback : it->second;
}

} // namespace mkwvk
