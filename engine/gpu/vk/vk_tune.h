// (better-aa) Live switches for A/B tests while the game runs (vk_tune.cpp): RX_VK_TUNE=<file> names a file of key=value
// lines, read again whenever it changes (looked at every 250 ms at most). A key that is not there gives the caller's
// fallback, so with no file everything is as without it. For a test in a place that takes a while to reach (a crawl
// tunnel), where a restart would lose it.
#pragma once

#include <atomic>
#include <chrono>
#include <cstdint>

namespace mkwvk {

/// key's value in the RX_VK_TUNE file, or fallback (no file, no such key, or not a number)
int tune_int(const char* key, int fallback);

/// (better-aa) tune_int for a hot path (a draw's): its value asked again at most every 250 ms, an atomic read between.
/// One per call site: `static TuneHot t{"key", fallback}; t.get()`
struct TuneHot {
    const char* key;
    int fallback;
    std::atomic<int> v{0};
    std::atomic<int64_t> next{0};
    TuneHot(const char* k, int fb) : key(k), fallback(fb), v(fb) {}
    int get() {
        const int64_t now = std::chrono::steady_clock::now().time_since_epoch().count();
        if (now >= next.load(std::memory_order_relaxed)) {
            next.store(now + 250000000, std::memory_order_relaxed);
            v.store(tune_int(key, fallback), std::memory_order_relaxed);
        }
        return v.load(std::memory_order_relaxed);
    }
};

} // namespace mkwvk
