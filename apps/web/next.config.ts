import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  async headers() {
    return [{
      source: "/(.*)",
      headers: [
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "X-Frame-Options", value: "DENY" },
        { key: "Referrer-Policy", value: "no-referrer" },
        { key: "Permissions-Policy", value: "camera=(), geolocation=(), microphone=()" },
        // Next.js emits inline RSC hydration/bootstrap scripts for the App Router.
        // Keep the policy same-origin and disallow object/frame injection while
        // allowing those framework bootstrap scripts to execute.
        { key: "Content-Security-Policy", value: "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self' http: https:; frame-ancestors 'none'; base-uri 'self'" },
      ],
    }];
  },
};

export default nextConfig;
