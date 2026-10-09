import { afterEach, expect, it, vi } from "vitest";
import { AdminDiscoverController } from "@/components/admin-discover-state";

const account = {
  id: "12345678-1234-4234-9234-123456789012",
  display_name: "Test admin",
  created_at: "2026-10-09",
};
const controllers: AdminDiscoverController[] = [];

function response(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status });
}

function start(enabled = false) {
  // This controller runs only in the browser, through the authenticated Next proxy.
  vi.stubGlobal("window", {});
  const fetch = vi.fn<typeof globalThis.fetch>().mockImplementation(async (url) => {
    if (String(url).endsWith("/me")) return response({ data: account });
    if (String(url).endsWith("/capabilities")) {
      return response({ data: { optimizer: false, recommendations: enabled } });
    }
    return response({ flag: "recommendations", account_id: account.id, enabled: !enabled });
  });
  vi.stubGlobal("fetch", fetch);
  const controller = new AdminDiscoverController();
  controllers.push(controller);
  controller.start();
  return { controller, fetch };
}

afterEach(() => {
  controllers.forEach((controller) => controller.stop());
  controllers.length = 0;
  vi.unstubAllGlobals();
});

it("loads this account's capability without changing flags or generating", async () => {
  const { controller, fetch } = start(true);
  await vi.waitFor(() =>
    expect(controller.getSnapshot()).toMatchObject({ enabled: true, error: null }),
  );
  expect(controller.getSnapshot().account).toEqual(account);
  await controller.refresh();
  expect(
    fetch.mock.calls.map(([url]) => new URL(String(url), "http://localhost").pathname),
  ).toEqual(["/api/v1/me", "/api/v1/capabilities", "/api/v1/me", "/api/v1/capabilities"]);
  expect(fetch.mock.calls.every(([, options]) => !options?.method)).toBe(true);
});

it.each([false, true])("explicitly changes only this account's access from %s", async (enabled) => {
  const { controller, fetch } = start(enabled);
  await vi.waitFor(() => expect(controller.getSnapshot().enabled).toBe(enabled));
  await controller.setEnabled(!enabled);
  expect(fetch).toHaveBeenLastCalledWith("/api/v1/admin/feature-flags/recommendations", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled: !enabled, account_id: account.id }),
  });
  expect(controller.getSnapshot()).toMatchObject({ enabled: !enabled, saving: false, error: null });
  expect(fetch.mock.calls.some(([url]) => String(url).includes("/runs"))).toBe(false);
});

it("does not write before loading, while saving, or after unmount", async () => {
  const { controller, fetch } = start();
  await controller.setEnabled(true);
  expect(fetch).toHaveBeenCalledTimes(2);
  await vi.waitFor(() => expect(controller.getSnapshot().enabled).toBe(false));
  let settle!: (value: Response) => void;
  fetch.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        settle = resolve;
      }),
  );
  const pending = controller.setEnabled(true);
  await controller.setEnabled(true);
  expect(fetch).toHaveBeenCalledTimes(3);
  controller.stop();
  settle(response({ flag: "recommendations", account_id: account.id, enabled: true }));
  await pending;
  await controller.setEnabled(true);
  expect(fetch).toHaveBeenCalledTimes(3);
  expect(controller.getSnapshot().enabled).toBe(false);
});

it.each(["http", "network", "wrong-account", "wrong-flag", "wrong-value", "malformed"])(
  "requires a read-only refresh after an uncertain %s save failure",
  async (failure) => {
    const { controller, fetch } = start();
    await vi.waitFor(() => expect(controller.getSnapshot().enabled).toBe(false));
    if (failure === "network") fetch.mockRejectedValueOnce(new Error("Connection lost"));
    else {
      const replies: Record<string, Response> = {
        http: response({}, 403),
        "wrong-account": response({ flag: "recommendations", account_id: "other", enabled: true }),
        "wrong-flag": response({ flag: "optimizer", account_id: account.id, enabled: true }),
        "wrong-value": response({
          flag: "recommendations",
          account_id: account.id,
          enabled: false,
        }),
        malformed: new Response("not JSON"),
      };
      fetch.mockResolvedValueOnce(replies[failure]!);
    }
    await controller.setEnabled(true);
    expect(controller.getSnapshot()).toMatchObject({ enabled: null, saving: false });
    expect(controller.getSnapshot().error).toContain("Refresh status");
    await controller.setEnabled(true);
    expect(fetch).toHaveBeenCalledTimes(3);
    await controller.refresh();
    expect(controller.getSnapshot()).toMatchObject({ enabled: false, error: null });
    expect(fetch.mock.calls.filter(([, options]) => options?.method === "PUT")).toHaveLength(1);
  },
);

it("shows load errors and supports a read-only retry", async () => {
  const { controller, fetch } = start();
  await vi.waitFor(() => expect(controller.getSnapshot().enabled).toBe(false));
  fetch.mockRejectedValueOnce(new Error("Status unavailable"));
  await controller.refresh();
  expect(controller.getSnapshot()).toMatchObject({ enabled: null, error: "Status unavailable" });
  await controller.setEnabled(true);
  expect(fetch.mock.calls.some(([, options]) => options?.method === "PUT")).toBe(false);
  await controller.refresh();
  expect(controller.getSnapshot()).toMatchObject({ enabled: false, error: null });
});

it("does not claim disabled access when the deployed backend omits the capability", async () => {
  const { controller, fetch } = start();
  await vi.waitFor(() => expect(controller.getSnapshot().enabled).toBe(false));
  fetch.mockImplementation(async (url) =>
    response({ data: String(url).endsWith("/me") ? account : { optimizer: false } }),
  );
  await controller.refresh();
  expect(controller.getSnapshot().enabled).toBeNull();
  expect(controller.getSnapshot().error).toContain("backend");
});
