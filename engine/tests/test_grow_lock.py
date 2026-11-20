"""The parallel replay's dry pass appends render conditions and uniform updates while early segments read them, without
waiting behind the workers' reads (gpu/vk/vk_replay.cpp; RX_VK_GROW_LOCK_PLAIN=1: as before).

With RX_VK_SEG_EARLY the dry pass appends to par_conds and ub_updates while workers read entries appended before their
segment was handed out. Every append took ub_grow_mu exclusively and every worker read held it shared; the lock lets new
readers in while a writer waits, so an append waited 4-7 us among four workers' reads (3.1 ms a frame in Zora's Domain for
the render conditions alone). Now a condition's append takes the lock only when it moves the vector's buffer (room is
reserved at each dry pass's start), the workers read a published count (par_conds_n) instead of the vector's size, and an
update's append is let in ahead of the reads that begin after it asks (ub_grow_waiting).

The guards, par_conds_reset, the condition's append and the worker's read are cut out of the source and compiled with
stubs: a writer thread appends 200,000 conditions (and an update every 10) while four reader threads read conditions and
walk the updates under their guards, every value checked; with the switch unset, 0 and 1, and with the reserved room cut
to 64 entries so that appends move the buffer under the lock. And, by the text: both dry passes reset par_conds with room,
the worker reads par_conds_n, the switch is documented.

(better-aa) par_conds and ub_updates are StableSeqs: blocks that never move, so neither an append nor a worker's read takes the
lock by default (RX_VK_UB_LOCK=1: the guards as above, for an A/B). The fixture cuts StableSeq and ub_lock_on out of the source
too, stands for ub_updates with a StableSeq, and runs with RX_VK_UB_LOCK unset and 1, each with RX_VK_GROW_LOCK_PLAIN unset, 0
and 1.

python -I -B tests/test_grow_lock.py --cxx <compiler>
"""
import argparse
import os
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def block(source, marker, start=0):
    start = source.index(marker, start)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    source = (ROOT / "gpu/vk/vk_replay.cpp").read_text(encoding="utf-8")

    plain = block(source, "bool grow_lock_plain() {")
    if 'getenv("RX_VK_GROW_LOCK_PLAIN")' not in plain:
        raise SystemExit("FAIL: grow_lock_plain does not read RX_VK_GROW_LOCK_PLAIN")
    stable_at = source.index("template <class T, size_t kBlock = 256, size_t kBlocks = 16384>\nclass StableSeq {")
    stable = block(source, "template <class T, size_t kBlock = 256, size_t kBlocks = 16384>", stable_at) + ";"
    lock_on = block(source, "bool ub_lock_on() {")
    if 'getenv("RX_VK_UB_LOCK")' not in lock_on:
        raise SystemExit("FAIL: ub_lock_on does not read RX_VK_UB_LOCK")
    reset = block(source, "void par_conds_reset() {")
    waiting = re.search(r"std::atomic<bool> ub_grow_waiting\{false\};", source)
    if not waiting:
        raise SystemExit("FAIL: no ub_grow_waiting")
    read_guard = block(source, "struct UbReadGuard {") + ";"
    grow_guard = block(source, "struct UbGrowGuard {") + ";"
    marker = "if (grow_lock_plain()) {   // (better-aa: par_conds is a StableSeq"
    append_at = source.index(marker)
    first = block(source, marker, append_at)
    rest = source[append_at + len(first):]
    if not rest.lstrip().startswith("else {"):
        raise SystemExit("FAIL: the condition's append has no lock-free branch")
    other = block(rest, "else {")
    publish = "par_conds_n.store(par_conds.size(), std::memory_order_release);"
    after = rest[rest.index(other) + len(other):]
    if not after.lstrip().startswith(publish):
        raise SystemExit("FAIL: the count is not published right after the condition's append")
    append = first + " " + other + "\n" + publish
    if append.count("UbGrowGuard ug;") != 1 or not re.search(r"\} else \{\s*par_conds\.push_back", append):
        raise SystemExit("FAIL: the condition's append is not as expected (the guard only when the buffer moves)")
    read = "s.render_enabled = cond_at < par_conds_n.load(std::memory_order_acquire) ? par_conds[cond_at] != 0 : true;"
    if read not in source:
        raise SystemExit("FAIL: a worker does not read the render condition by the published count")
    if "cond_at < par_conds.size()" in source:
        raise SystemExit("FAIL: a worker still reads par_conds' size")
    if source.count("par_points.clear(), par_conds_reset(), dry_work = 0;") != 2 or "par_conds.clear()" in source.replace(reset, ""):
        raise SystemExit("FAIL: a dry pass does not reset par_conds")
    if "StableSeq<uint8_t, 4096, 1024> par_conds;" not in source or "StableSeq<UbUpdate> ub_updates;" not in source:
        raise SystemExit("FAIL: par_conds and ub_updates are not StableSeqs")
    docs = (ROOT / "docs/development.md").read_text(encoding="utf-8")
    if "RX_VK_GROW_LOCK_PLAIN" not in docs:
        raise SystemExit("FAIL: RX_VK_GROW_LOCK_PLAIN is not in docs/development.md")

    fixture = r'''
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <mutex>
#include <shared_mutex>
#include <thread>
#include <chrono>
#include <memory>
#include <vector>
static void logf(const char*, ...) {}
@STABLE@
@LOCK_ON@
enum class Mode { Serial, Dry, Worker };
thread_local Mode rmode = Mode::Serial;
StableSeq<uint8_t, 4096, 1024> par_conds;
std::atomic<size_t> par_conds_n{0};
std::shared_mutex ub_grow_mu;
std::atomic<bool> ub_growing{false};
thread_local int ub_read_depth = 0;
@PLAIN@
@RESET@
@WAITING@
@READ_GUARD@
@GROW_GUARD@
struct State { bool render_enabled = true; };
StableSeq<uint64_t> updates;                  // (stands for ub_updates: appended under UbGrowGuard)
std::atomic<size_t> updates_n{0};
void append_cond(bool on) {
    State s;
    s.render_enabled = on;
    @APPEND@
}
bool read_cond(size_t cond_at) {
    State s;
    UbReadGuard ug;
    @READ@
    return s.render_enabled;
}
static bool want(size_t i) { return (i * 2654435761u >> 7) % 3 != 0; }
int main() {
    const size_t N = 200000;
    par_conds_reset();
    ub_growing.store(true);
    std::atomic<bool> stop{false};
    std::atomic<long> bad{0}, reads{0};
    std::atomic<int> ready{0};   // (the writer starts once every reader runs: on a busy Windows test machine the writer
                                 //  could finish its 200,000 appends before a reader was scheduled, and the check counted no reads)
    std::vector<std::thread> readers;
    for (int t = 0; t < 4; t++)
        readers.emplace_back([&, t] {
            rmode = Mode::Worker;
            ready++;
            unsigned x = 12345u + t;
            while (!stop.load()) {
                const size_t n = par_conds_n.load(std::memory_order_acquire);
                if (n) {
                    x = x * 1103515245u + 12345u;
                    const size_t i = x % n;
                    if (read_cond(i) != want(i)) bad++;
                }
                {
                    UbReadGuard ug;   // (a uniform read: the updates appended so far walked)
                    const size_t m = updates_n.load(std::memory_order_acquire);
                    for (size_t k = m > 8 ? m - 8 : 0; k < m; k++)
                        if (updates[k] != k * 7) bad++;
                }
                reads++;
                /* (the plain switch's baseline: glibc's rwlock prefers a waiting reader, so with four readers on four CPUs
                   every shared hold is taken again before the writer can, and its append waits forever. The game's workers
                   read at their draws, not in a tight loop: a short sleep after each read leaves the writer the gaps it
                   would have. The default path is left at full pressure) */
                if (grow_lock_plain()) std::this_thread::sleep_for(std::chrono::microseconds(20));
            }
        });
    while (ready.load() < 4) std::this_thread::yield();
    rmode = Mode::Dry;
    for (size_t i = 0; i < N; i++) {
        append_cond(want(i));
        if (i % 10 == 0) {
            UbGrowGuard ug;
            updates.push_back(updates.size() * 7);
            updates_n.store(updates.size(), std::memory_order_release);
        }
    }
    for (int s = 0; s < 2000 && reads.load() < 100; s++) std::this_thread::sleep_for(std::chrono::milliseconds(1));
    stop = true;
    for (auto& r : readers) r.join();
    ub_growing.store(false);
    if (par_conds.size() != N || par_conds_n.load() != N) { std::printf("count %zu/%zu\n", par_conds.size(), par_conds_n.load()); return 1; }
    for (size_t i = 0; i < N; i++)
        if ((par_conds[i] != 0) != want(i)) { std::printf("entry %zu\n", i); return 1; }
    if (bad) { std::printf("%ld wrong reads\n", bad.load()); return 1; }
    if (reads < 100) { std::printf("readers starved (%ld reads)\n", reads.load()); return 1; }
    par_conds_reset();
    if (!par_conds.empty() || par_conds_n.load() != 0) { std::printf("reset\n"); return 1; }
    std::printf("ok %ld reads\n", reads.load());
    return 0;
}
'''
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("stableseq",):
            src = (fixture.replace("@STABLE@", stable).replace("@LOCK_ON@", lock_on)
                   .replace("@PLAIN@", plain).replace("@RESET@", reset)
                   .replace("@WAITING@", waiting.group(0)).replace("@READ_GUARD@", read_guard)
                   .replace("@GROW_GUARD@", grow_guard).replace("@APPEND@", append).replace("@READ@", read))
            cpp = os.path.join(tmp, name + ".cpp")
            exe = os.path.join(tmp, name + (".exe" if os.name == "nt" else ""))
            Path(cpp).write_text(src, encoding="utf-8")
            r = subprocess.run([args.cxx, "-std=c++17", "-O2", "-pthread", cpp, "-o", exe], capture_output=True, text=True)
            if r.returncode:
                raise SystemExit("FAIL: the fixture does not compile:\n" + r.stderr[-3000:])
            for ub_lock in (None, "1"):
                for switch in (None, "0", "1"):
                    env = dict(os.environ)
                    env.pop("RX_VK_GROW_LOCK_PLAIN", None)
                    env.pop("RX_VK_UB_LOCK", None)
                    if switch is not None:
                        env["RX_VK_GROW_LOCK_PLAIN"] = switch
                    if ub_lock is not None:
                        env["RX_VK_UB_LOCK"] = ub_lock
                    r = subprocess.run([exe], capture_output=True, text=True, env=env, timeout=120)
                    if r.returncode:
                        raise SystemExit(f"FAIL ({name}, RX_VK_UB_LOCK={ub_lock}, RX_VK_GROW_LOCK_PLAIN={switch}): {r.stdout.strip()}")
    print("PASS: the dry pass's appends among the workers' reads, every value read as written, with and without the switch")


if __name__ == "__main__":
    main()
