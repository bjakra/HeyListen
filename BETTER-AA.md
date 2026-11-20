# HeyListen better-aa

A fork of [HeyListen](https://github.com/Sacrappy/HeyListen) v0.4.2 (branch `better-aa`) that improves anti-aliasing,
frame generation and input latency, mainly for AMD GPUs on Linux. All changes are in the Vulkan back end
(`engine/gpu/vk`, built as `hookshot_vk.so` / `hookshot_vk.dll`), so a game folder built by HeyListen v0.4.2 takes the new
back end without a rebuild.

## What it adds

- **FSR Native AA (100%).** AMD FSR 3.1 and AMD FSR 4 get a *Native AA (100%)* step on the Render resolution row, ahead
  of Quality: the 3D is drawn at the output's full size and FSR only smooths its edges. Before, a saved 100% was drawn
  at 67% (`upscaler_rows.h`).
- **Custom render scale.** Render resolution gets a *Custom* step (after Native AA for FSR, after 100% for the game's
  own upscaler) and a *Custom render scale* slider, 50 to 100% in 1% steps, applied live and saved as
  `custom_render_scale`. The exact share reaches the game (85% draws 2176x1224 at 1440p), not the nearest twelfth.
- **Sharpness inside the upscaler.** The Sharpness row now drives FSR's own RCAS: FSR 4 through its dispatch, FSR 3.1
  through AMD's `accumulate_sharpen` and `rcas` passes. The 3D is sharpened before the HUD, and the window pass leaves
  its own sharpening out while an upscaler sharpens. `RX_VK_UPSCALER_SHARPEN=0` restores the old behaviour.
- **AMD Anti-Lag 2.** A new *AMD Anti-Lag 2* row (saved as `amd_anti_lag`) through `VK_AMD_anti_lag`, on AMD's driver or
  Mesa's `VK_LAYER_MESA_anti_lag` (enabled by the renderer on Linux, `RX_VK_ANTILAG=-` leaves it alone). It keeps working
  with frame generation: only the game's own frames get a present stage.
- **FSR 3.1 frame generation that holds up.** Three causes of the heavy ghosting are fixed:
  1. The frame interpolation shaders were compiled with `FFX_FRAMEINTERPOLATION_OPTION_LOW_RESOLUTION_MOTION_VECTORS`,
     which the SDK does not read (it reads `LOW_RES_`): render-size motion was sampled at display-size positions.
  2. The game draws its HUD into the picture, so the HUD moved with the scene. The gameplay upscale's picture is now
     copied before the HUD is drawn and given to FSR as its HUD-less colour (`shaders/fg_hud.comp`), with AMD's passes
     patched to keep the HUD in place (`scripts/fsr3_shaders.py` FI_PATCHES).
  3. Only the camera's motion reached the interpolation; the temporal chain's motion, with the skinned characters' own,
     is now copied over it (`fsr3_inputs::take_motion`, when an FSR 4 / DLSS engine draws the upscale).

  FSR 3.1 now makes the frames at any multiplier (2x to 8x) and at Auto, each at its own time between two game frames.
  A *Frame generation by* row picks AMD FSR 3.1 (default) or the built-in blend.
- **The right scene depth for motion vectors.** The game has no motion vectors: the renderer makes them from the scene's
  depth and camera. Some places draw the picture with two depth buffers (the Kokiri Sword's crawl tunnel, parts of the
  forest): the game goes on to a second depth partway through the frame, and only that one lines up with the picture.
  The first draw's depth used to be taken, and in the tunnel the motion was off by 9-31 px (median; the true motion was
  0-4 px), which tore the ceiling's roots apart in every frame FSR 3.1 made and fed FSR 4 / DLSS bad history. Every pass of
  the frame is kept now and the depth the game switched to last for the upscale's input is used (`scene_pass.h`):
  measured against block matching of the frames themselves, 1.2 px median, 4.1 px at the 90th percentile.
- **The upscaler off the game's wait (+19% with FSR 4 on an RX 6800).** Every frame the game reads back GPU results (the
  light meter's sums and a few small buffers) and waits for them, and that wait used to last to the end of the frame's whole
  submission: the GPU work after the upscale too, AMD FSR 4's INT8 network (~3.8 ms on an RX 6800) and the post and HUD
  passes. Every GPU write the game reads back is made before the upscale (`RX_VK_RB_ORDER_LOG=1` with `RX_VK_PARALLEL=0`
  logs them in recording order against the upscale's place), so the replay now ends a part of the recording right before
  the upscale's dispatch, with the write-backs made so far and a number of its own on the recordings' timeline
  (`vk_replay.cpp upscale_go_on`). The game's readbacks and the next capture's late pages wait for that part when every
  page they need was written back by it (`vk_memory.cpp wb_early`), else for the submission's end as before. The GPU then
  runs the upscale while the game's CPU goes on with its next frame. Kokiri Forest, 1440p, FSR 4 at 50%, no frame
  generation, the same save, alternated live three times: 46.6 -> 55.3 fps; a readback's wait 4.6 -> 0.24 ms; the picture
  the same, and no light-meter pulses (80 frames each: the largest frame-to-frame change of the scene's mean brightness
  0.64 of 255 against 0.75 without). `RX_VK_TUNE`'s `upscale_cut=0` turns it off; `fsr_defer=1` was the measurement that
  bounded it (the engine's work moved to the present: the gain without the cut, the picture wrong).
- **The renderer's chain on the P-cores (Linux, hybrid Intel CPUs: +7%).** A trace of the frame's hand-offs
  (`HOS_JOBTRACE` and `tools/bench/critpath.py`) put 17.6 ms of a 20.4 ms frame on the Presentation Thread, most of it
  waiting in the present for the frame's replay; the game's own threads were idle most of the frame. perf showed the
  replay's threads running 10-16% of their time on the E-cores. The replay workers and the order thread now run on the
  P-cores only (`/sys/devices/cpu_core/cpus`), and a thread's replay or present runs there too, its own placement put
  back after (`vk_replay.cpp pcore_set`, `ReplayPin`). The game's threads are left to the scheduler: putting those on
  the P-cores as well was 1.5 fps worse. i5-12600KF, Kokiri, 1440p, the same save, two restarts each: 50.0 -> 53.7 fps,
  the slowest 5 s 48.8 -> 53.0. `RX_VK_PCORE_PIN=0` turns it off; a CPU without `cpu_core` (AMD, older Intel) is left
  as it was.
- **The uniform-update list read without a lock (+2.8%).** While the planning (dry) pass still runs, early segments
  are already recorded on the workers, and they read the frame's uniform-buffer updates and render-condition results
  the pass is still appending. Those lists were a `std::deque` / `std::vector`, whose index may move on an append, so
  every append took a lock exclusively and every read took it shared. perf's sleep stacks of the replay threads showed
  the workers sleeping ~800 times a frame in `ub_read` / `ub_overlay` and the planning pass ~210 times waiting to
  append, on the frame's critical path. Both are now a `StableSeq` (`vk_replay.cpp`): blocks that never move, reached
  through a fixed table; an append writes only new places and publishes its count last, so a worker reads the entries
  it was handed with no lock. Kokiri, 1440p, two restarts each: 53.4 -> 54.9 fps, the picture the same.
  `RX_VK_UB_LOCK=1` brings the lock back for an A/B.
- **Global memory reads through the page table first (GPU -3%).** The game's heaviest shaders read memory through pointers
  the translator cannot tie to one buffer. Eden lowers each such read to a search over every storage buffer the stage has
  (a nested chain of 64-bit range tests and branches), with HeyListen's guest page table only as the last fallback. The
  driver's own statistics (`RX_VK_PIPE_STATS=<program keys>`, below) showed what that costs: Kokiri's most expensive draw,
  one fullscreen pass at 720p, is 22,481 instructions with 1,341 branches for 421 such reads, and a compute pass 28,878
  instructions with 689 spilled scalar registers. Now a read goes to the page table first (a range test, the table's
  entry, the load), and the search is left only for what the table does not map. Both reach the same memory: the
  table points at the mirrors the buffers are bound from. That 720p pass went from 0.38 to 0.26 ms and the compute pass
  from 0.29 to 0.20 ms. Over the frame the GPU time went 13.5 -> 13.1 ms and the frame rate 60.3 -> 61.4 (four runs
  each, the picture the same). On by default on RADV in stages that write no storage memory (`RX_VK_FOLLOW_FIRST=0`:
  off, `=2`: every stage, 12.8 ms but no higher frame rate). It is part of the program cache's stamp, so a change of
  it translates the shaders again.
- **Turn on Resizable BAR (+17%; a firmware setting, not code).** Without it the CPU sees 256 MB of VRAM, and RADV keeps
  every buffer resident: that window sat full, and each kernel submit (`DRM_IOCTL_AMDGPU_CS`, ~30 a frame) spent up to
  0.5-2 ms in amdgpu's range-limited VRAM allocator, which kept Mesa's submit thread 42% busy while the GPU waited for work.
  With "Above 4G Decoding" and "Re-Size BAR Support" on (`mem_info_vis_vram_total` = all VRAM), Kokiri, 1440p, Native AA,
  on the headless output: 64.0 -> 75.0 fps (three runs), GPU 13.4 -> 10.8 ms, submits 1.67 s -> 0.39 s per 4 s, none over
  256 us. (Capping batches at 8 command buffers, +2% before, does nothing now.)
- **No storage-buffer search after the page table (GPU -6%, +4% fps).** With the table first, each global load still
  carried Eden's search as the fallback for what the table does not map, inlined at every load: Kokiri's heaviest compute
  pass ee7764a6 was 147 KB of code with 218 spilled registers, its 720p fragment pass da7a7ab2 122 KB with 86, several
  times RDNA2's instruction cache. Now (`RX_VK_FOLLOW_FIRST=3`, RADV's default) every stage that follows pointers reads
  through the table, and an address it does not map reads 0 (and goes to the miss log): 49 KB and 41 KB, no spills. The
  table covers every pool a storage buffer can be bound from, at the same device address; to check, `RX_VK_FOLLOW_AUDIT=1`
  (with `RX_VK_FOLLOW_FIRST=2 RX_VK_MISS_LOG=2 RX_VK_MISS_KEEP=1`) logs any load the search held after a table miss, with
  bit 63 set: none over a save's load and minutes of play, compute, vertex and fragment stages. Kokiri, 1440p, Native AA,
  three runs each: GPU 14.1 -> 13.3 ms, 62.2 -> 64.7 fps (on the monitor too: 13.85 -> 13.05 ms, 63.2 -> 64.7).
  `RX_VK_FOLLOW_FIRST=1` brings back the table-first-then-search of above.
- **Finer recording segments on 16-thread CPUs (+3.4%).** The renderer's timeline (`RX_VK_TL_S`, `tools/tl_classify.py`)
  showed the GPU idle while the Presentation Thread recorded medium command buffers alone, ~2 ms each. Fine segments
  (up to 10 of ~128 draws, more than there are recorders) were on only under 16 hardware threads; now also at 16.
  i5-12600KF, two runs each: 61.05 -> 63.15 fps (80-draw segments in one round: 62.4). `RX_VK_FINE_SEGMENTS=0`: off.
- **Diagnostics added for the GPU work:** `RX_VK_PIPE_STATS=<key prefixes>` logs the driver's statistics of those
  programs' pipelines (registers, spills, instructions, branches; `VK_KHR_pipeline_executable_properties`), and
  `RX_VK_PIPE_IR=<folder>` writes their NIR, ACO IR and disassembly. `RX_VK_PROGRAM_CACHE_TAG=<tag>` gives a
  translation switch a program cache of its own (`hookshot_programs_<tag>.bin`): one cache per A/B arm, so the arms do
  not translate everything again on each start. For a clean A/B also set `RX_VK_NO_PREDICT=1` and
  `MESA_SHADER_CACHE_MAX_SIZE=8G`: otherwise the background pipeline prediction keeps four threads compiling for many
  minutes after a switch, and the frame rate drops from 60 to the mid 40s.
- **Tried, no gain on RADV:** a full barrier's source scope from the work recorded since the last one
  (`RX_VK_BARRIER_SRC=1`: of ~550 barriers a frame, ~300 lose the colour and depth cache flush), GPU 13.85 -> 13.80 ms,
  the frame rate the same: the drain is the cost, not the flush. Faster capture scans (`RX_VK_COLLECT_FAST=1` with
  `RX_VK_CAPTURE_SCAN_SPLIT=1` or `RX_VK_CAPTURE_PRECOPY=1`), 96-draw segments, `RX_VK_SEG_MAX=12` (-10%): inside the
  noise or slower. `RX_VK_MISS_LOG=2` puts the miss log in vertex and fragment stages too, `RX_VK_MISS_KEEP=1` keeps its
  counts from the start instead of from the capture's frame.
- **Tried after Resizable BAR, no gain (75 fps, GPU 10.8 ms).** The frame is now the Presentation Thread's serial loop
  (`HOS_JOBTRACE` + `tools/bench/critpath.py`, `chainb.py`: 13.2 of a 13.8 ms frame, its submits 11.8 ms) with the GPU ring
  91% busy (`gpu_scheduler` trace: ~12.1 ms a frame, ~31 jobs, the idle ~1 ms in one gap a frame while the next work is
  recorded). Inside the noise or slower, three restarts each: no batching (`RX_VK_BATCH=0`), at most 8 command buffers a
  batch, sending held submits while the GPU is still on its last batch (a test knob, depth 2/3), the segments batched too
  (one kernel job instead of ~20 a frame: 74.8 -> 59.9 fps, 66.3 at depth 2, 73.2 at depth 3: held work starves the
  ring), `RADV_PERFTEST=cswave32` / `localbos`, the left-out-range check without its mutex (~10% of the segment
  workers' time in perf, none of the frame), FSR 4 in wave64 (`FSR4_VK_INT8_MODEL_WAVE32=0`, GPU -0.1 ms). FSR 4 Native
  AA is 2.8 ms of the GPU frame (`RX_VK_PASS_TIMING=1`), most of it its pre- and post-pass.
- **Recompiler changes, exact but not faster here.** Tested and kept, but they measured inside the noise on this PC
  (the old binary 51.5, the new 51.8 fps, three restarts each), because the game's code is not on the frame's critical
  path here:
  - NEON TBL / TBX become one `pshufb` + blend per table register (SSE4.1) instead of a byte loop through the stack,
    695 sites in the animation code's hot functions (`recomp_tbl`, `tests/test_tbl.py`: every form against the Arm
    rule, both paths, 0 mismatches);
  - the sdk's `memcpy` / `memmove` / `memset` / `memcmp` / `bcmp` / `strlen` / `strcmp` (and `__memcpy_aarch64`) run as
    host code (`host/nn_libc.c`, HLE; `RX_GUEST_LIBC=1` at the lift leaves them lifted);
  - a function that is one branch to a PLT stub is called as that stub's target (`a64_lift.py find_veneers`, 1351 of
    them; `A64_VENEER=0`: off);
  - the hot pieces built with `-fsplit-machine-functions` (Linux, with the profile; `RX_SPLIT_COLD=0`: off), and
    `sqrtf` on the hot list.
  `tools`-side: the whole game is rebuilt from this tree with `make_game.py --update` and the AppImage's toolchain.
- **Live switches for tests** (`vk_tune.h`): `RX_VK_TUNE=<file>` of `key=value` lines, read again while the game runs:
  frame generation's passes (`fsr_fg`, `fg_hud_copy`, `fg_keep_static`, `fg_chain_motion`, `fg_debug`), the motion view
  (`debug_motion`), the scene pass rule (`cam_pass`, `cam_depth_id`) and logs (`cam_log`, `pass_log`), the upscale cut
  (`upscale_cut`, `fsr_defer`), and `mv_dump=<n>`,
  which writes the next n frames' colour, depth, motion and camera to `RX_VK_MV_DUMP_DIR` for an offline check.

## Not possible here

- **AMD FSR 4 frame generation** is machine-learned and AMD ships it for RX 9000 GPUs only; on older GPUs AMD's own API
  falls back to FSR 3.1 frame generation, which this fork uses.
- **Intel XeSS** (super resolution and frame generation): Intel's SDK (3.0.2) ships Windows binaries only, and XeSS frame
  generation is DirectX 12 only. There is no Linux `libxess.so` to load.

## Building on Linux

The Vulkan back end alone, with the clang, Python and sysroot from the HeyListen v0.4.2 AppImage and the headers
`engine/scripts/linux/deps.sh` lists (Vulkan-Headers v1.4.345, SPIRV-Headers vulkan-sdk-1.4.341.0, VMA v3.3.0):

```sh
cd engine
EMSDK=<appimage>/usr/lib/hookshot/emsdk RX_CPM=<cpm headers> HOOKSHOT_SYSROOT=<appimage>/usr/lib/hookshot/sysroot \
OOT_WORK=<work dir> RX_MARCH=x86-64-v3 RX_VK_ONLY=1 RX_RELEASE=1 HOOKSHOT_FSR=1 \
    <appimage>/usr/python/bin/python3 -I nx2/build.py --standalone --jobs 14
# -> <work dir>/sa/build/hookshot_vk.so: copy it over <game folder>/bin/hookshot_vk.so
```

AMD FSR 4 on Linux needs a Vulkan FSR 4 library beside the game, e.g. one built from
[fsr4-vk](https://github.com/ebuwiz/fsr4-vk) (INT8 on RDNA 2 and 3).

## Credits and licence

HeyListen is GPL-3.0-or-later. `vk_antilag.*`, `vk_fsr3fi.*`, `vk_builtin_spv.*`, `shaders/fg_hud.comp`,
`scripts/fsr3_shaders.py` and the frame generation changes in `vk_framegen.cpp`, `vk_draw.cpp` and `vk_fsr3_inputs.cpp`
are ported from [Longshot](https://git.magicbean.dev/MagicBeanDev/Longshot) (commit 868f6be871, GPL-3.0), so this fork
as a whole is distributed under GPL-3.0. AMD's FidelityFX SDK sources are MIT (`engine/third_party/fidelityfx-sdk`).
