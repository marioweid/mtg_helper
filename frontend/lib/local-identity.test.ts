import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { localIdentityEnabled } from "@/lib/local-identity";
import { getAppUser, getBackendHeaders } from "@/lib/app-identity";
import { apiClient } from "@/lib/api";

const { google } = vi.hoisted(() => ({ google: vi.fn() }));
vi.mock("@/auth", () => ({ auth: google }));

function local() {
  vi.stubEnv("LOCAL_DEV_AUTH", "true");
  vi.stubEnv("APP_ENV", "local");
  vi.stubEnv("NODE_ENV", "development");
  vi.stubEnv("BACKEND_ORIGIN", "http://backend:8000");
}
beforeEach(() => {
  google.mockReset();
  vi.stubEnv("LOCAL_DEV_AUTH", "false");
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("Local identity guard", () => {
  it("defaults off, and requires both an isolated development runtime and backend", () => {
    expect(localIdentityEnabled({})).toBe(false);
    local();
    expect(localIdentityEnabled()).toBe(true);
  });
  it.each([
    { APP_ENV: "live" },
    { APP_ENV: "staging" },
    { APP_ENV: "production" },
    { NODE_ENV: "production" },
    { BACKEND_ORIGIN: "https://hosted.example" },
  ])("refuses unsafe runtime settings %j", (patch) => {
    const environment = {
      LOCAL_DEV_AUTH: "true",
      APP_ENV: "local",
      NODE_ENV: "development",
      BACKEND_ORIGIN: "http://backend:8000",
      ...patch,
    };
    expect(() => localIdentityEnabled(environment)).toThrow("isolated local development");
  });
});

describe("Application identity", () => {
  it("uses no Google or invented bearer token locally", async () => {
    local();
    const headers = await getBackendHeaders();
    expect(headers?.has("authorization")).toBe(false);
    expect(google).not.toHaveBeenCalled();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json({
          data: { id: "account", email: "dev@local.test", display_name: "Developer" },
        }),
      ),
    );
    expect(await getAppUser()).toEqual({
      id: "account",
      email: "dev@local.test",
      name: "Developer",
    });
  });
  it("authenticates server-rendered API requests through the same local mode", async () => {
    local();
    const fetcher = vi.fn(async () => Response.json({ data: { id: "account" } }));
    vi.stubGlobal("fetch", fetcher);
    expect((await apiClient.getMe()).id).toBe("account");
    const [url, options] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://backend:8000/api/v1/me");
    expect(new Headers(options.headers).has("authorization")).toBe(false);
    expect(google).not.toHaveBeenCalled();
  });
  it("retains Google bearer auth normally and rejects absent or failed sessions", async () => {
    google.mockResolvedValue({ idToken: "google-token", user: { email: "google@test.local" } });
    expect((await getBackendHeaders())?.get("authorization")).toBe("Bearer google-token");
    expect(await getAppUser()).toMatchObject({ email: "google@test.local" });
    google.mockResolvedValue(null);
    expect(await getBackendHeaders()).toBeNull();
    google.mockResolvedValue({ idToken: "expired", error: "RefreshFailed" });
    expect(await getBackendHeaders()).toBeNull();
  });
});
