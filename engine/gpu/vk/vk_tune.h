// (better-aa) Live switches for A/B tests while the game runs (vk_tune.cpp): RX_VK_TUNE=<file> names a file of key=value
// lines, read again whenever it changes (looked at every 250 ms at most). A key that is not there gives the caller's
// fallback, so with no file everything is as without it. For a test in a place that takes a while to reach (a crawl
// tunnel), where a restart would lose it.
#pragma once

namespace mkwvk {

/// key's value in the RX_VK_TUNE file, or fallback (no file, no such key, or not a number)
int tune_int(const char* key, int fallback);

} // namespace mkwvk
