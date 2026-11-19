// (better-aa) scene_pass.h: the frame's scene passes, and the one picked for the upscale
#include "../gpu/vk/scene_pass.h"

#include <cstdio>

#define CHECK(name, condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL %s at line %d\n", name, __LINE__); return 1; } } while (0)

namespace mkwvk {
struct Texture {
    int id;
};
}  // namespace mkwvk

int main() {
    using mkwvk::Texture;
    namespace sp = mkwvk::scene_pass;
    Texture outer{1}, inner{2}, depth_a{3}, depth_b{4}, small{5};
    sp::Passes p;
    bool fresh = false;
    CHECK("no pass", p.pick(&inner, 1) == -1);
    // (the tunnel's frame: 4 draws into (outer, A), then 2 into (inner, B), then 1 more into (outer, A))
    CHECK("first draw makes a pass", p.note(7, &outer, &depth_a, 100, 50, &fresh) == 0 && fresh);
    for (int i = 0; i < 3; i++) CHECK("the same pass", p.note(7, &outer, &depth_a, 100, 50, &fresh) == 0 && !fresh);
    CHECK("another pass", p.note(7, &inner, &depth_b, 100, 50, &fresh) == 1 && fresh);
    CHECK("its second draw", p.note(7, &inner, &depth_b, 100, 50, &fresh) == 1 && !fresh);
    CHECK("back to the first", p.note(7, &outer, &depth_a, 100, 50, &fresh) == 0 && !fresh);
    CHECK("counts", p.n == 2 && p.pass[0].draws == 5 && p.pass[1].draws == 2);
    CHECK("rule 0: the first drawn", p.pick(&inner, 0) == 0);
    CHECK("rule 1: the upscale's input", p.pick(&inner, 1) == 1 && p.pick(&outer, 1) == 0);
    CHECK("rule 1 without a match: the last drawn", p.pick(&small, 1) == 0);
    CHECK("rule 2: the last drawn", p.pick(&inner, 2) == 0);
    CHECK("rule 3: the most draws", p.pick(&inner, 3) == 0);
    CHECK("rule 4: begun last", p.pick(&inner, 4) == 1);
    CHECK("the default is rule 4", sp::kRule == 4);
    // (a smaller target is never picked over the scene's size)
    CHECK("a smaller pass", p.note(7, &small, &depth_b, 50, 25, &fresh) == 2 && fresh);
    CHECK("the largest only", p.pick(&small, 1) == 0);
    {   // (rule 4: the tunnel's two depths on one picture, a third pass on another target begun later still)
        sp::Passes t;
        Texture picture{10}, other{11}, first{12}, second{13};
        t.note(3, &picture, &first, 100, 50, &fresh);
        for (int i = 0; i < 300; i++) t.note(3, &picture, &first, 100, 50, &fresh);
        t.note(3, &picture, &second, 100, 50, &fresh);
        t.note(3, &picture, &first, 100, 50, &fresh);   // (interleaved: the first goes on to the end)
        t.note(3, &other, &first, 100, 50, &fresh);
        CHECK("rule 4: the input's pass begun last", t.pick(&picture, 4) == 1);
        CHECK("rule 4: no pass on the input: begun last of all", t.pick(&small, 4) == 2);
        CHECK("rule 2 picks the other target there", t.pick(&picture, 2) == 2);
    }
    // (a new frame starts over)
    CHECK("new frame", p.note(8, &inner, &depth_b, 100, 50, &fresh) == 0 && fresh && p.n == 1);
    for (int i = 0; i < sp::kMax + 2; i++) p.note(9, &outer, reinterpret_cast<const Texture*>(&outer) + i + 1, 100, 50, &fresh);
    CHECK("no more than kMax kept", p.n == sp::kMax && p.note(9, &inner, &depth_a, 100, 50, &fresh) == -1);
    std::printf("scene_pass: all checks passed\n");
    return 0;
}
