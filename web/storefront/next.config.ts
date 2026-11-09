import type { NextConfig } from "next";

// Where the Django backend runs. Dev default only; set BACKEND_ORIGIN per environment.
const backendOrigin = process.env.BACKEND_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // The Docker build sets NEXT_OUTPUT=standalone for a small, self-contained server.
  // Off by default, so local builds (including Windows) are unaffected.
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  transpilePackages: ["@sk/ui", "@sk/api-client"],
  images: { formats: ["image/avif", "image/webp"] },
  // Django endpoints end in a slash. Do not let Next strip it with a redirect.
  skipTrailingSlashRedirect: true,
  // Same-origin API calls keep session cookies, CSRF and the Origin check simple.
  // Production routing is Agent A's call.
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${backendOrigin}/api/v1/:path*` },
    ];
  },
};

export default nextConfig;