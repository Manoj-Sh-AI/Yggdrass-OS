import { NextRequest } from "next/server";

// Public downloads contain signed application code only. Publishing uses the
// existing owner session; no new deployment password or privileged token.
export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  return proxy(request, (await context.params).path.join("/"));
}
export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  return proxy(request, (await context.params).path.join("/"));
}
async function proxy(request: NextRequest, path: string) {
  const publishing = request.method === "POST";
  if (
    publishing
      ? path !== "publish"
      : !/^(manifest|android|assets\/[a-f0-9]{64}|apk\/[a-f0-9]{64}\.apk)$/.test(
          path,
        )
  )
    return Response.json(
      { detail: "Unknown update endpoint." },
      { status: 404 },
    );
  if (
    publishing &&
    !request.headers.get("authorization")?.startsWith("Bearer ")
  )
    return Response.json({ detail: "Sign in to publish." }, { status: 401 });
  const length = request.headers.get("content-length");
  if (
    publishing &&
    (!length || !/^\d+$/.test(length) || Number(length) > 100 * 1024 * 1024)
  )
    return Response.json({ detail: "Invalid release size." }, { status: 413 });
  const headers = new Headers();
  for (const name of [
    "expo-platform",
    "expo-runtime-version",
    "expo-protocol-version",
    "expo-current-update-id",
    "expo-expect-signature",
    "accept",
  ])
    if (request.headers.has(name))
      headers.set(name, request.headers.get(name)!);
  if (publishing) {
    headers.set("Authorization", request.headers.get("authorization")!);
    headers.set("Content-Type", "application/zip");
    headers.set("Content-Length", length!);
  }
  try {
    const root = process.env.YGGDRESS_API_URL || "http://127.0.0.1:8100";
    const upstream = await fetch(`${root}/v1/mobile-updates/${path}`, {
      method: request.method,
      headers,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(publishing ? 120000 : 30000),
      ...(publishing ? { body: request.body, duplex: "half" } : {}),
    } as RequestInit);
    const responseHeaders = new Headers({
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    });
    for (const name of [
      "content-type",
      "content-disposition",
      "content-length",
      "expo-protocol-version",
      "expo-sfv-version",
      "expo-signature",
      "expo-manifest-filters",
    ])
      if (upstream.headers.has(name))
        responseHeaders.set(name, upstream.headers.get(name)!);
    return new Response(upstream.status === 204 ? null : upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return Response.json(
      {
        detail: "Update service unavailable. Your installed app is unchanged.",
      },
      { status: 503 },
    );
  }
}
