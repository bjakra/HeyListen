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
- **Live switches for tests** (`vk_tune.h`): `RX_VK_TUNE=<file>` of `key=value` lines, read again while the game runs:
  frame generation's passes (`fsr_fg`, `fg_hud_copy`, `fg_keep_static`, `fg_chain_motion`, `fg_debug`), the motion view
  (`debug_motion`), the scene pass rule (`cam_pass`, `cam_depth_id`) and logs (`cam_log`, `pass_log`), and `mv_dump=<n>`,
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
