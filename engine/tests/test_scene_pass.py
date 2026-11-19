"""(better-aa) The scene's passes of a frame (gpu/vk/scene_pass.h): each kept, and the one the temporal upscalers and AMD
FSR 3.1's inputs take their camera and depth from picked at the upscale (test_scene_pass.cpp checks the rules by
behaviour). No game or GPU required.

python -I -B tests/test_scene_pass.py [--cxx g++]
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cxx", default="g++")
    args = ap.parse_args()
    for name in ("vk_temporal.cpp", "vk_fsr3_inputs.cpp"):
        source = (ROOT / "gpu" / "vk" / name).read_text()
        if "s.passes.note(" not in source or "pick_pass(s, in)" not in source:
            raise SystemExit("%s does not keep the frame's scene passes and pick one at the upscale" % name)
    with tempfile.TemporaryDirectory(prefix="scene-pass-") as tmp:
        exe = Path(tmp) / "scene-pass"
        subprocess.run([args.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror", str(ROOT / "tests" / "test_scene_pass.cpp"),
                        "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
