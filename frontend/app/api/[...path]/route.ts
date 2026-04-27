import { auth } from "@/auth";
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const BACKEND = process.env["BACKEND_ORIGIN"] ?? "http://localhost:8000";

const HOP_BY_HOP = new Set([
  "connection",
  "content-length",
  "host",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "transfer-encoding",
  "upgrade",
]);

async function forward(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await ctx.params;
  if (path[0] === "auth") {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }

  const session = await auth();
  if (!session || session.error === "RefreshFailed" || !session.idToken) {
    return NextResponse.json(
      { error: { code: "UNAUTHENTICATED", message: "sign in required" } },
      { status: 401 },
    );
  }

  const url = `${BACKEND}/api/${path.join("/")}${req.nextUrl.search}`;
  const headers = new Headers();
  for (const [key, value] of req.headers.entries()) {
    if (!HOP_BY_HOP.has(key.toLowerCase())) headers.set(key, value);
  }
  if (session.idToken) headers.set("authorization", `Bearer ${session.idToken}`);

  const init: RequestInit & { duplex?: "half" } = {
    method: req.method,
    headers,
    redirect: "manual",
  };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = req.body;
    init.duplex = "half";
  }

  const upstream = await fetch(url, init);
  const respHeaders = new Headers(upstream.headers);
  respHeaders.delete("content-encoding");
  respHeaders.delete("content-length");
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: respHeaders,
  });
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
export const PATCH = forward;
export const DELETE = forward;
