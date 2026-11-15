import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
const assets = new Set([
  "graph.html",
  "vis-network.min.js",
  "three.js",
  "3d-force-graph.min.js",
  "inter-latin-400-normal.woff2",
  "inter-latin-600-normal.woff2",
]);
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ asset: string }> },
) {
  const { asset } = await params;
  if (!assets.has(asset))
    return NextResponse.json(
      { detail: "Unknown graph asset." },
      { status: 404 },
    );
  const root = process.env.YGGDRESS_API_URL || "http://127.0.0.1:8101";
  try {
    const response = await fetch(`${root}/v1/graph/assets/${asset}`, {
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(20000),
      headers: { Cookie: request.headers.get("cookie") || "" },
    });
    if (!response.ok)
      return NextResponse.json(
        {
          detail:
            response.status === 401
              ? "Sign in to view your graph."
              : "The Brain graph is unavailable. Retry when its viewer is ready.",
        },
        { status: response.status },
      );
    const headers = new Headers({
      "Content-Type":
        response.headers.get("content-type") || "application/octet-stream",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
      "Cross-Origin-Resource-Policy": "same-origin",
    });
    if (asset === "graph.html") {
      headers.set(
        "Content-Security-Policy",
        "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data: blob:; connect-src 'none'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'",
      );
      const html = (await response.text())
        .replace(
          "</head>",
          '<link rel="stylesheet" href="/graph-embed.css"></head>',
        )
        .replace("</body>", '<script src="/graph-embed.js"></script></body>');
      return new Response(html, { headers });
    }
    return new Response(response.body, { headers });
  } catch {
    return NextResponse.json(
      { detail: "The Brain graph service is unavailable. Please retry." },
      { status: 503 },
    );
  }
}
