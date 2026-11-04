import type { NextConfig } from "next";

// Where the Django backend runs. Dev default only; set BACKEND_ORIGIN per environment.
const backendOrigin = process.env.BACKEND_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  transpilePackages: ["@sk/ui", "@sk/api-client"],
  images: { formats: ["image/avif", "image/webp"] },
  // Django endpoints end in a slash. Do not let Next strip it with a redirect.
  skipTrailingSlashRedirect: true,
  // Same-origin API calls keep session cookies, CSRF and the Origin check simple.
  // Proposal only, see open question 4 in the report. Production routing is Agent A's call.
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${backendOrigin}/api/v1/:path*` },
    ];
  },
};

export default nextConfig;
