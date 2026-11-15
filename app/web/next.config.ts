import type { NextConfig } from "next";
// Candidate builds must never overwrite the directory currently being served.
const candidate = process.env.YGGDRESS_BUILD_DIR;
if (candidate && !/^\.next(?:-[a-z0-9-]+)?$/.test(candidate)) {
  throw new Error(
    "YGGDRESS_BUILD_DIR must name a dedicated .next build directory.",
  );
}
const config: NextConfig = {
  // Verify a production build without overwriting the running local preview.
  distDir:
    candidate ||
    (process.env.YGGDRESS_VERIFY_BUILD === "1" ? ".next-verify" : ".next"),
  poweredByHeader: false,
  devIndicators: false,
  turbopack: { root: process.cwd() },
};
export default config;
