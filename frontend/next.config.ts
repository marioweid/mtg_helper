import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  webpack(config, { nextRuntime }) {
    if (nextRuntime === "edge") {
      // JOSE's guarded compression helpers are unused: Auth.js issues JWTs without a zip header.
      // Keep other Edge warnings visible; do not change authentication's execution runtime.
      config.ignoreWarnings = [
        ...(config.ignoreWarnings ?? []),
        {
          module: /jose[/\\]dist[/\\]webapi[/\\]lib[/\\]deflate\.js/,
          message: /A Node\.js API is used \((?:CompressionStream|DecompressionStream)\b/,
        },
      ];
    }
    return config;
  },
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "cards.scryfall.io",
      },
    ],
  },
};

export default nextConfig;
