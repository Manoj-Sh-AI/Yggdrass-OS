export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code?: string,
    public extra?: { completed?: number; canUndo?: boolean },
  ) {
    super(message);
  }
}
let csrf: string | undefined;
export async function applicationApi<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const unsafe = init.method && init.method !== "GET";
  if (unsafe && !path.startsWith("auth/login") && !csrf) {
    const session = await applicationApi<{ csrf: string }>("auth/session");
    csrf = session.csrf;
  }
  const response = await fetch(`/api/backend/${path}`, {
    ...init,
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(unsafe ? { "X-Yggdress-CSRF": csrf || "" } : {}),
      ...init.headers,
    },
  });
  const data = await response
    .json()
    .catch(() => ({ detail: "Application service unavailable." }));
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("auth/"))
      window.location.assign("/login");
    throw new ApiError(
      response.status,
      typeof data.detail === "string"
        ? data.detail
        : "The request could not be completed.",
      data.code,
      { completed: data.completed, canUndo: data.canUndo },
    );
  }
  return data as T;
}
export async function logout() {
  await applicationApi("auth/logout", { method: "POST", body: "{}" });
  csrf = undefined;
  window.location.assign("/login");
}
