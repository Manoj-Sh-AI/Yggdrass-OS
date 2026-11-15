import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
const python = fileURLToPath(
  new URL(
    process.platform === "win32"
      ? "../../api/.venv/Scripts/python.exe"
      : "../../api/.venv/bin/python",
    import.meta.url,
  ),
);
const script = fileURLToPath(
  new URL("../../api/scripts/browser_check.py", import.meta.url),
);
const result = spawnSync(python, [script, ...process.argv.slice(2)], {
  stdio: "inherit",
});
if (result.error)
  console.error(
    "Install the application API test environment first: uv sync --project app/api",
  );
process.exit(result.status ?? 1);
