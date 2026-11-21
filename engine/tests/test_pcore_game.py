"""The P-cores the game's frame threads keep to on a Linux hybrid CPU (host/hos_thread.c parse_cpu_list, pcore_game_thread).

parse_cpu_list reads the kernel's CPU lists (/sys/devices/cpu_core/cpus: "0-11" on an i5-12600KF, "0-15" on an i7-13700K)
into a mask of the first 64 logical processors; pcore_game_thread names the threads that are pinned there.

python -I -B tests/test_pcore_game.py [--cxx clang++]
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def block(text, marker):
    start = text.index(marker)
    end = text.index('{', start) + 1
    depth = 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--source', type=Path, default=ROOT / 'host/hos_thread.c')
    args = parser.parse_args()
    text = args.source.read_text(encoding='utf-8')
    helpers = block(text, 'static uint64_t parse_cpu_list(') + '\n' + block(text, 'static int pcore_game_thread(')
    fixture = r'''
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#define CHECK(ok) do { if (!(ok)) { std::fprintf(stderr, "failed line %d\n", __LINE__); std::exit(1); } } while (0)
''' + helpers + r'''
int main() {
    CHECK(parse_cpu_list("0-11\n") == 0xFFFull);           // i5-12600KF's P-cores
    CHECK(parse_cpu_list("0-15") == 0xFFFFull);            // i7-13700K's
    CHECK(parse_cpu_list("0,2,4-7\n") == 0xF5ull);
    CHECK(parse_cpu_list("12-15") == 0xF000ull);
    CHECK(parse_cpu_list("60-70") == 0xF000000000000000ull);   // (past 64: left out)
    CHECK(parse_cpu_list("") == 0);
    CHECK(parse_cpu_list("x") == 0);
    CHECK(pcore_game_thread("sead::MainThread"));
    CHECK(pcore_game_thread("BaseProcExecutor3"));
    CHECK(pcore_game_thread("ModuleSystemWorker5"));
    CHECK(pcore_game_thread("Presentation Thread"));
    CHECK(!pcore_game_thread("hos audio renderer"));
    CHECK(!pcore_game_thread("NavMeshCAStepDelegate"));
    return 0;
}
'''
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / 't.cpp'
        exe = Path(tmp) / 't'
        src.write_text(fixture, encoding='utf-8')
        subprocess.run([args.cxx, '-std=c++20', '-Wall', '-Wextra', '-Werror', str(src), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
    print('pcore_game: ok')


if __name__ == '__main__':
    main()
