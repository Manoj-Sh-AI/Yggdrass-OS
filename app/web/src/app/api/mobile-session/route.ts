import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

/** POST only: credentials never enter navigation URLs, page scripts or logs. */
export async function POST(request: NextRequest) {
  const origin = process.env.YGGDRESS_ORIGIN;
  let authorization = request.headers.get("authorization") || "";
  const suppliedOrigin = request.headers.get("origin");
  // Android WebView postUrl does not forward custom headers. A bounded form POST
  // supplies the same revocable device token without exposing it to a page URL.
  if (!authorization) {
    if (Number(request.headers.get("content-length") || 0) > 512)
      return NextResponse.json(
        { detail: "Request too large." },
        { status: 413 },
      );
    const body = await request.text();
    if (body.length > 512)
      return NextResponse.json(
        { detail: "Request too large." },
        { status: 413 },
      );
    authorization = "Bearer " + (new URLSearchParams(body).get("token") || "");
  }
  if (
    !origin ||
    (suppliedOrigin &&
      suppliedOrigin !== "null" &&
      suppliedOrigin !== origin) ||
    !/^Bearer [A-Za-z0-9_-]{40,100}$/.test(authorization)
  )
    return NextResponse.json(
      { detail: "Mobile sign-in required." },
      { status: 403 },
    );
  const target = request.nextUrl.searchParams.get("view");
  if (target !== "notes" && target !== "graph")
    return NextResponse.json(
      { detail: "Unknown mobile view." },
      { status: 404 },
    );
  try {
    const upstream = await fetch(
      `${process.env.YGGDRESS_API_URL || "http://127.0.0.1:8100"}/v1/mobile/webview-session`,
      {
        method: "POST",
        headers: { Authorization: authorization, Origin: origin },
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(12000),
      },
    );
    if (!upstream.ok)
      return NextResponse.json(
        { detail: "Your mobile session expired. Sign in again." },
        { status: upstream.status },
      );
    const response = NextResponse.redirect(new URL(`/${target}`, origin), 303);
    for (const cookie of upstream.headers.getSetCookie())
      response.headers.append("Set-Cookie", cookie);
    response.headers.set("Cache-Control", "no-store");
    response.headers.set("Referrer-Policy", "no-referrer");
    return response;
  } catch {
    return NextResponse.json(
      { detail: "The application service is unavailable." },
      { status: 503 },
    );
  }
}
