import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
const script = fileURLToPath(new URL("./mobile-release.py", import.meta.url));
const python = fileURLToPath(
  new URL(
    process.platform === "win32"
      ? "../../api/.venv/Scripts/python.exe"
      : "../../api/.venv/bin/python",
    import.meta.url,
  ),
);
if (!existsSync(python)) {
  throw new Error(
    "Install the application API's Python environment before publishing mobile updates.",
  );
}
const result = spawnSync(python, [script, ...process.argv.slice(2)], {
  stdio: "inherit",
  windowsHide: true,
});
if (result.error) throw result.error;
process.exit(result.status ?? 1);
