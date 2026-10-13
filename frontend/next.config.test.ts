import type { NextConfig } from "next";
import { expect, it } from "vitest";

import nextConfig from "@/next.config";

type BuildContext = Parameters<NonNullable<NextConfig["webpack"]>>[1];

it("ignores only JOSE optional compression warnings in Edge, preserving other warnings", () => {
  const prior = () => false;
  const configure = nextConfig.webpack;
  if (!configure) throw new Error("Webpack configuration is missing");
  const result = configure({ ignoreWarnings: [prior] }, { nextRuntime: "edge" } as BuildContext);
  expect(result.ignoreWarnings[0]).toBe(prior);
  const rule = result.ignoreWarnings[1];
  expect(rule.module.test("/node_modules/jose/dist/webapi/lib/deflate.js")).toBe(true);
  expect(rule.module.test("C:\\node_modules\\jose\\dist\\webapi\\lib\\deflate.js")).toBe(true);
  expect(rule.module.test("/node_modules/other/dist/deflate.js")).toBe(false);
  expect(rule.message.test("A Node.js API is used (CompressionStream at line: 10)")).toBe(true);
  expect(rule.message.test("A Node.js API is used (DecompressionStream at line: 26)")).toBe(true);
  expect(rule.message.test("A Node.js API is used (process.cwd at line: 10)")).toBe(false);
});

it.each(["nodejs", undefined])("does not suppress warnings outside Edge: %s", (nextRuntime) => {
  const configure = nextConfig.webpack;
  if (!configure) throw new Error("Webpack configuration is missing");
  const original = { ignoreWarnings: [] };
  expect(configure(original, { nextRuntime } as BuildContext)).toBe(original);
  expect(original.ignoreWarnings).toEqual([]);
});
