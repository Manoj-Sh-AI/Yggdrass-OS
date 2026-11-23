import { phaseFor, sceneImages, sceneKey, seasonFor } from "../src/scenes";

describe("scene selection (mirrors the web clock fallback)", () => {
  it("maps months to seasons, flipped south of the equator", () => {
    expect(seasonFor(10)).toBe("autumn");
    expect(seasonFor(0)).toBe("winter");
    expect(seasonFor(3)).toBe("spring");
    expect(seasonFor(6, -33)).toBe("winter");
  });
  it("splits the day at 06:00, 09:00 and 18:00", () => {
    expect(phaseFor(359)).toBe("night");
    expect(phaseFor(360)).toBe("sunrise");
    expect(phaseFor(540)).toBe("afternoon");
    expect(phaseFor(1080)).toBe("night");
  });
  it("builds a key that always has a bundled image", () => {
    const key = sceneKey(new Date(2026, 10, 18, 14, 0));
    expect(key).toBe("autumn-afternoon-clear");
    expect(Object.keys(sceneImages)).toHaveLength(24);
    expect(sceneImages[key]).toBeDefined();
  });
});
