import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { AdminDiscoverControls, AdminDiscoverPanel } from "@/components/admin-discover-panel";
import type { AdminDiscoverState } from "@/components/admin-discover-state";

const state: AdminDiscoverState = {
  account: { id: "account", display_name: "Test admin", created_at: "2026-10-09" },
  enabled: false,
  loading: false,
  saving: false,
  error: null,
};

function render(patch: Partial<AdminDiscoverState>) {
  return renderToStaticMarkup(
    <AdminDiscoverControls
      state={{ ...state, ...patch }}
      onToggle={() => {}}
      onRefresh={() => {}}
    />,
  );
}

it("labels account-only access, free browsing, paid Generate and how to find the tab", () => {
  const html = render({ enabled: true });
  expect(html).toContain("Disable for my account");
  expect(html).toContain("Test admin · Enabled");
  expect(html).toContain("Other accounts are unchanged");
  expect(html).toContain("Enabling and browsing do not call AI");
  expect(html).toContain("$0.10/run");
  expect(html).toContain("in-flight request may still bill");
  expect(html).toContain("Open a deck (reload if already open)");
});

it("offers an explicit enable action when disabled and no automatic saving on render", () => {
  expect(render({})).toContain("Enable for my account");
  const html = renderToStaticMarkup(<AdminDiscoverPanel />);
  expect(html).toContain("Unknown");
  expect(html).toMatch(/disabled=""[^>]*>Enable for my account/);
});

it.each([
  { loading: true },
  { saving: true },
  { enabled: null, error: "Refresh status before trying again" },
  { account: null },
])("disables changing access when unavailable: %j", (patch) => {
  const html = render(patch);
  expect(html).toMatch(/disabled=""[^>]*>Enable for my account/);
  if (patch.error) expect(html).toContain('role="alert"');
});
