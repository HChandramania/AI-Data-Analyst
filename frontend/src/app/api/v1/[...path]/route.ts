import { randomUUID } from "node:crypto";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

async function proxy(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const id = randomUUID();
  const permitted = ["auth", "datasets", "conversations", "analyses", "dashboards", "search"].includes(path[0]) ||
    (path.join("/") === "reports/export" && request.method === "POST") ||
    (path[0] === "health" && path.length === 2 && ["live", "ready", "metrics"].includes(path[1]));
  const failure = (status: number, code: string, message: string) => NextResponse.json({
    request_id: id, error: { code, message, details: {} },
  }, { status, headers: { "X-Request-ID": id, "Cache-Control": "no-store" } });
  if (!permitted) return failure(404, "HTTP_404", "Resource not found.");
  try {
    const backend = new URL(process.env.BACKEND_URL ?? "http://127.0.0.1:8000");
    if (!["http:", "https:"].includes(backend.protocol) || backend.username || backend.password) {
      throw new Error("Invalid backend configuration");
    }
    const headers = new Headers();
    for (const name of ["cookie", "content-type", "x-csrf-token", "origin"]) {
      const value = request.headers.get(name);
      if (value) headers.set(name, value);
    }
    let body: ArrayBuffer | undefined;
    if (["POST", "PUT", "PATCH"].includes(request.method) && request.body) {
      const reader = request.body.getReader();
      const chunks: ArrayBuffer[] = [];
      const limit = path[0] === "datasets" ? 256 * 1024 * 1024 : 1024 * 1024;
      let size = 0;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > limit) {
          await reader.cancel();
          return failure(413, "REQUEST_TOO_LARGE", "Request exceeds size limit.");
        }
        chunks.push(value.slice().buffer as ArrayBuffer);
      }
      body = await new Blob(chunks).arrayBuffer();
    }
    const upstream = await fetch(new URL(`/api/v1/${path.join("/")}`, backend), {
      method: request.method, headers, body, redirect: "error", cache: "no-store",
      signal: AbortSignal.timeout(path[0] === "datasets" ? 210000 : 120000),
    });
    const responseHeaders = new Headers({ "Cache-Control": "no-store",
      "X-Request-ID": upstream.headers.get("X-Request-ID") ?? id });
    const contentType = upstream.headers.get("content-type");
    const attachment = upstream.headers.get("content-disposition");
    const report = path.join("/") === "reports/export" && request.method === "POST" && upstream.ok &&
      contentType?.startsWith("text/html") && /^attachment; filename="[a-zA-Z0-9_-]+\.html"$/.test(attachment ?? "");
    if (!contentType?.startsWith("application/json") && !report) {
      return failure(502, "INVALID_BACKEND_RESPONSE", "The backend returned an invalid response.");
    }
    responseHeaders.set("Content-Type", contentType!);
    if (report) {
      responseHeaders.set("Content-Disposition", attachment!);
      responseHeaders.set("X-Content-Type-Options", "nosniff");
    }
    for (const cookie of upstream.headers.getSetCookie()) responseHeaders.append("Set-Cookie", cookie);
    return new NextResponse(upstream.body, { status: upstream.status, headers: responseHeaders });
  } catch {
    return failure(503, "BACKEND_UNAVAILABLE", "The backend could not be reached. Try again shortly.");
  }
}

export const GET = proxy;
export const POST = proxy;
export const DELETE = proxy;
export const PATCH = proxy;
