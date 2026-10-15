import { NextRequest, NextResponse } from "next/server";

export async function proxy(request: NextRequest) {
  const target = new URL("/api/v1/auth/me", process.env.BACKEND_URL ?? "http://127.0.0.1:8000");
  try {
    const response = await fetch(target, {
      headers: { cookie: request.headers.get("cookie") ?? "" },
      cache: "no-store", redirect: "error", signal: AbortSignal.timeout(5000),
    });
    if (response.ok) return NextResponse.next();
  } catch { /* Login page offers retry when the service returns. */ }
  return NextResponse.redirect(new URL("/login", request.url));
}

export const config = { matcher: ["/analyze/:path*", "/datasets/:path*", "/dashboards/:path*"] };
