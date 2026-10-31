import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest, NextResponse } from "next/server";
import type { NextFetchEvent } from "next/server";
import middleware from "@/middleware";
import { GET } from "@/app/api/[...path]/route";

const { state } = vi.hoisted(() => ({ state: { session: null as { idToken: string } | null } }));
vi.mock("@/auth", () => ({
  auth: (handler?: (request: NextRequest & { auth: unknown }) => unknown) =>
    handler
      ? (request: NextRequest) => handler(Object.assign(request, { auth: state.session }))
      : Promise.resolve(state.session),
}));

beforeEach(() => {
  state.session = null;
  vi.stubEnv("LOCAL_DEV_AUTH", "false");
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});
function local() {
  vi.stubEnv("LOCAL_DEV_AUTH", "true");
  vi.stubEnv("APP_ENV", "local");
  vi.stubEnv("NODE_ENV", "development");
  vi.stubEnv("BACKEND_ORIGIN", "http://backend:8000");
}

describe("Page middleware", () => {
  it("leaves API authentication to its route so anonymous requests get 401, not HTML", async () => {
    const response = await middleware(
      new NextRequest("http://localhost:3000/api/v1/me"),
      {} as NextFetchEvent,
    );
    expect(response?.status).toBe(200);
    expect(response?.headers.get("location")).toBeNull();
  });
  it("lets explicit local development through without a Google session", async () => {
    local();
    const response = await middleware(
      new NextRequest("http://localhost:3000/decks"),
      {} as NextFetchEvent,
    );
    expect(response?.status).toBe(200);
    expect(response?.headers.get("location")).toBeNull();
  });
  it("retains the normal sign-in redirect and Google session access", async () => {
    const request = new NextRequest("http://localhost:3000/decks");
    const anonymous = await middleware(request, {} as NextFetchEvent);
    expect(anonymous?.headers.get("location")).toContain("/signin?callbackUrl=%2Fdecks");
    state.session = { idToken: "google" };
    const authenticated = await middleware(new NextRequest(request.url), {} as NextFetchEvent);
    expect(authenticated?.status).toBe(200);
  });
});

describe("Browser API proxy", () => {
  it("forwards local requests without accepting a caller-supplied identity token", async () => {
    local();
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json({ data: { id: "local" } }));
    vi.stubGlobal("fetch", fetcher);
    const response = await GET(
      new NextRequest("http://localhost:3000/api/v1/me", {
        headers: { authorization: "Bearer forged" },
      }),
      { params: Promise.resolve({ path: ["v1", "me"] }) },
    );
    expect(response.status).toBe(200);
    expect(new Headers(fetcher.mock.calls[0]?.[1]?.headers).has("authorization")).toBe(false);
  });
  it("rejects unauthenticated normal requests and forwards a real Google session token", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(NextResponse.json({ data: { id: "google" } }));
    vi.stubGlobal("fetch", fetcher);
    const context = { params: Promise.resolve({ path: ["v1", "me"] }) };
    const request = new NextRequest("http://localhost:3000/api/v1/me");
    expect((await GET(request, context)).status).toBe(401);
    expect(fetcher).not.toHaveBeenCalled();
    state.session = { idToken: "google" };
    expect((await GET(request, context)).status).toBe(200);
    expect(new Headers(fetcher.mock.calls[0]?.[1]?.headers).get("authorization")).toBe(
      "Bearer google",
    );
  });
});
