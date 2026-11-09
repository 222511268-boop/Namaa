import type { NextConfig } from "next";

// The browser only talks to this Next.js server; /api/* is forwarded to the FastAPI backend so the
// session cookie stays first-party. BACKEND_URL is fixed at build time (Docker build argument).
const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  experimental: {
    // OpenStreetMap imports can take a few minutes when Overpass is busy (the backend caps its own
    // retries below this limit). The default rewrite proxy timeout is 30 s.
    proxyTimeout: 300_000,
  },
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
};

export default nextConfig;
