import { NextRequest, NextResponse } from "next/server";
export const dynamic = "force-dynamic";
const allowed =
  /^(auth\/(login|logout|session)|application\/(tasks(\/[a-zA-Z0-9-]+)?|routine(\/actions)?|planning(\/commands)?)|notes\/(search|create|undo|items\/[a-zA-Z0-9_-]+(\/preview)?|previews\/[a-zA-Z0-9_-]+\/(confirm|cancel))|brain\/(tree|notes(\/[a-zA-Z0-9_-]+(\/delete-(preview|confirm))?)?))$/;
async function proxy(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const path = (await params).path.join("/");
  const connections =
    /^application\/connections\/(capabilities|commands|from-note|notes\/[a-zA-Z0-9_-]{1,200}|(tasks|events)\/[a-fA-F0-9-]{36})$/;
  const chat =
    /^chat\/(capabilities|commands|conversations(\/[a-fA-F0-9-]{36}(\/export)?)?|attachments(\/[a-fA-F0-9-]{36})?)$/;
  const temporal = /^application\/time\/commands$/;
  const receivingUi =
    /^application\/(workflow\/(capabilities|reviews(\/resolve)?)|agents\/(status|reviews(\/resolve)?)|background(\/cancel)?|work-graph(\/roots)?)$/;
  const calendarContext =
    /^application\/connections\/calendar-context\/(date_item|availability)\/[a-fA-F0-9-]{36}$/;
  if (
    !allowed.test(path) &&
    !connections.test(path) &&
    !chat.test(path) &&
    !temporal.test(path) &&
    !receivingUi.test(path) &&
    !calendarContext.test(path) &&
    path !== "graph/status"
  )
    return NextResponse.json(
      { detail: "Unknown application endpoint." },
      { status: 404 },
    );
  const root = process.env.YGGDRESS_API_URL || "http://127.0.0.1:8100";
  const origin = request.headers.get("origin");
  const expectedOrigin = process.env.YGGDRESS_ORIGIN;
  if (
    !["GET", "HEAD"].includes(request.method) &&
    (!expectedOrigin || origin !== expectedOrigin)
  )
    return NextResponse.json(
      { detail: "Cross-origin changes are not allowed." },
      { status: 403 },
    );
  const length = Number(request.headers.get("content-length") || 0);
  const upload = path === "chat/attachments" && request.method === "POST";
  const download =
    /^chat\/attachments\/[a-fA-F0-9-]{36}$/.test(path) &&
    request.method === "GET";
  const maximum = upload ? 10 * 1024 * 1024 : 250000;
  if (!Number.isFinite(length) || length < 0 || length > maximum)
    return NextResponse.json({ detail: "Request too large." }, { status: 413 });
  try {
    let body: ArrayBuffer | undefined;
    if (!["GET", "HEAD"].includes(request.method) && request.body) {
      const reader = request.body.getReader();
      const chunks: Uint8Array[] = [];
      let size = 0;
      while (true) {
        const next = await reader.read();
        if (next.done) break;
        size += next.value.byteLength;
        if (size > maximum) {
          await reader.cancel();
          return NextResponse.json(
            { detail: "Request too large." },
            { status: 413 },
          );
        }
        chunks.push(next.value);
      }
      const bytes = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) {
        bytes.set(chunk, offset);
        offset += chunk.byteLength;
      }
      body = bytes.buffer;
    }
    const upstream = await fetch(
      `${root}/v1/${path}${request.nextUrl.search}`,
      {
        method: request.method,
        body,
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(path.startsWith("notes/") ? 60000 : 12000),
        headers: {
          "Content-Type": upload
            ? "application/octet-stream"
            : "application/json",
          Cookie: request.headers.get("cookie") || "",
          ...(origin ? { Origin: origin } : {}),
          "X-Yggdress-CSRF": request.headers.get("x-yggdress-csrf") || "",
          "X-Yggdress-Login": path === "auth/login" ? "1" : "",
        },
      },
    );
    const headers = new Headers({
      "Content-Type":
        download && upstream.ok
          ? upstream.headers.get("content-type") || "application/octet-stream"
          : "application/json",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    });
    for (const cookie of upstream.headers.getSetCookie())
      headers.append("Set-Cookie", cookie);
    if (download && upstream.ok) {
      headers.set(
        "Content-Disposition",
        upstream.headers.get("content-disposition") || "attachment",
      );
      headers.set("Content-Security-Policy", "sandbox; default-src 'none'");
    }
    return new Response(
      download && upstream.ok
        ? await upstream.arrayBuffer()
        : await upstream.text(),
      {
        status: upstream.status,
        headers,
      },
    );
  } catch {
    return NextResponse.json(
      {
        detail:
          "The application service is unavailable. Your data has not been replaced with a demo.",
      },
      { status: 503 },
    );
  }
}
export { proxy as GET, proxy as POST, proxy as PUT, proxy as PATCH };
