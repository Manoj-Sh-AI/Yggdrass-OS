type RetryStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;
const prefix = "yggdress.work.command.v1:";

// Retain only an opaque request fingerprint and UUID, never note/task text.
// This lets a failed/lost response be retried safely after a component remount.
export async function workspaceRetry(
  identity: string,
  fallback?: string,
  suppliedStorage?: RetryStorage,
) {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(identity),
  );
  const address =
    prefix +
    Array.from(new Uint8Array(digest), (value) =>
      value.toString(16).padStart(2, "0"),
    ).join("");
  let storage = suppliedStorage;
  let key = fallback || crypto.randomUUID();
  try {
    storage ||= window.sessionStorage;
    const previous = storage.getItem(address);
    if (
      previous &&
      /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(
        previous,
      )
    )
      key = previous;
    storage.setItem(address, key);
  } catch {
    /* In-memory retry remains available when browser storage is denied. */
  }
  return {
    key,
    complete: () => {
      try {
        storage?.removeItem(address);
      } catch {
        /* Optional storage. */
      }
    },
  };
}
