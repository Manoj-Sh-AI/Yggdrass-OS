import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
describe("approved editor dependency boundary", () => {
  it("pins the three official MPL-2.0 packages and preserves their license", () => {
    for (const name of ["core", "react", "ariakit"]) {
      const packageInfo = JSON.parse(
        readFileSync(
          new URL(
            `../node_modules/@blocknote/${name}/package.json`,
            import.meta.url,
          ),
          "utf8",
        ),
      );
      expect(packageInfo.version).toBe("0.57.0");
      expect(packageInfo.license).toBe("MPL-2.0");
      expect(
        readFileSync(
          new URL(
            `../node_modules/@blocknote/${name}/LICENSE`,
            import.meta.url,
          ),
          "utf8",
        ),
      ).toContain("Mozilla Public License Version 2.0");
    }
    expect(
      readFileSync(
        new URL("../public/licenses/blocknote/MPL-2.0.txt", import.meta.url),
        "utf8",
      ),
    ).toEqual(
      readFileSync(
        new URL("../node_modules/@blocknote/core/LICENSE", import.meta.url),
        "utf8",
      ),
    );
  });
  it("does not introduce BlockNote XL packages", () => {
    const lock = JSON.parse(
      readFileSync(new URL("../package-lock.json", import.meta.url), "utf8"),
    );
    expect(
      Object.keys(lock.packages).filter((name) =>
        name.includes("@blocknote/xl-"),
      ),
    ).toEqual([]);
    expect(
      readFileSync(
        new URL("../public/licenses/blocknote/NOTICE.txt", import.meta.url),
        "utf8",
      ),
    ).toContain("Unicode License V3");
  });
});
