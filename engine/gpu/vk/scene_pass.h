// (better-aa) The scene's passes of a frame, for the temporal upscalers' camera and depth (vk_temporal.cpp) and AMD FSR 3.1's
// inputs (vk_fsr3_inputs.cpp). A pass: the draws into one colour target and one depth with the scene's camera. Most frames
// have one; some have two of the same size and the same camera (the Kokiri Sword's crawl tunnel: from its first draw the
// game draws into the picture with one depth, ~400 draws; from about its 330th it draws into the same picture with a second
// depth too, ~100-300 draws, the two interleaved to the end), and only the second's is the picture's: the first's geometry
// does not line up with it at all. The first draw's pass used to win, the wrong one there: the motion from its depth was off
// by 9-33 px (median; true motion 0-4 px) and frame interpolation tore the scene apart. Every pass of the frame is kept
// instead, and the one to use is picked at the upscale, when its input is known (pick). No Vulkan: plain bookkeeping.
#pragma once

#include <cstdint>

namespace mkwvk {
struct Texture;

namespace scene_pass {

constexpr int kMax = 8;
/// The rule pick uses unless RX_VK_TUNE's cam_pass says another: 4. Measured in the tunnel (block matching of the chain's
/// colour against its motion, tools/mv_model.py; median / 90th percentile error): 0 (the first drawn) 9.4 / 56 px, 1 1.1 / 53
/// px (the last drawn flips between the two), 2 0.9 / 2.8 px, 3 (the most draws) 19.5 / 84 px; with no motion at all 2.0 px
constexpr int kRule = 4;

struct Pass {
    const Texture* color0 = nullptr;
    const Texture* depth = nullptr;
    uint32_t width = 0, height = 0;
    uint32_t draws = 0;
    uint64_t first = 0, last = 0;   // (the frame's order of its first and last draw)
};

struct Passes {
    uint64_t frame = ~0ull;
    uint64_t order = 0;
    Pass pass[kMax];
    int n = 0;

    /// A draw of frame now into (color0, depth): its pass's index, or -1 (more passes than kept). fresh: its first draw
    int note(uint64_t now, const Texture* color0, const Texture* depth, uint32_t width, uint32_t height, bool* fresh) {
        if (frame != now) frame = now, order = 0, n = 0;
        order++;
        *fresh = false;
        for (int i = 0; i < n; i++)
            if (pass[i].color0 == color0 && pass[i].depth == depth) {
                pass[i].draws++, pass[i].last = order;
                return i;
            }
        if (n == kMax) return -1;
        pass[n] = {color0, depth, width, height, 1, order, order};
        *fresh = true;
        return n++;
    }

    /// The pass to use for an upscale of in (its texture, at the scene's size) by rule, or -1 when the frame has none:
    /// the largest passes only (as before); among them 0: the first drawn (as before), 1: the one whose colour target is the
    /// upscale's input (else the last drawn), 2: the last drawn, 3: the most draws, 4: of those whose colour target is the
    /// upscale's input (all, when none is), the one begun last: the depth the game went on to for the picture
    int pick(const Texture* in, int rule) const {
        uint64_t area = 0;
        for (int i = 0; i < n; i++) area = pass[i].width * (uint64_t)pass[i].height > area ? pass[i].width * (uint64_t)pass[i].height : area;
        int best = -1;
        for (int i = 0; i < n; i++) {
            if (pass[i].width * (uint64_t)pass[i].height != area) continue;
            if (best < 0) {
                best = i;
                continue;
            }
            const Pass &p = pass[i], &b = pass[best];
            switch (rule) {
            case 1:
                if ((p.color0 == in) != (b.color0 == in)) {
                    if (p.color0 == in) best = i;
                } else if (p.last > b.last) {
                    best = i;
                }
                break;
            case 2: if (p.last > b.last) best = i; break;
            case 3: if (p.draws > b.draws) best = i; break;
            case 4:
                if ((p.color0 == in) != (b.color0 == in)) {
                    if (p.color0 == in) best = i;
                } else if (p.first > b.first) {
                    best = i;
                }
                break;
            default: if (p.first < b.first) best = i; break;
            }
        }
        return best;
    }
};

}  // namespace scene_pass
}  // namespace mkwvk
