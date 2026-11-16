// Vercel: exit 0 skips deployment; exit 1 permits its build.
const { YGGDRESS_RELEASE_APPROVED, YGGDRESS_API_URL, YGGDRESS_ORIGIN } =
  process.env;
const approved =
  YGGDRESS_RELEASE_APPROVED === "1" &&
  [YGGDRESS_API_URL, YGGDRESS_ORIGIN].every((value) => {
    try {
      const url = new URL(value);
      return url.protocol === "https:" && !url.username && !url.password;
    } catch {
      return false;
    }
  });
console.log(
  approved
    ? "Explicit release approval and HTTPS service configuration present."
    : "Deployment blocked: release review and HTTPS backend configuration are required.",
);
process.exit(approved ? 1 : 0);
