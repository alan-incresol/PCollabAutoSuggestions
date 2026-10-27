import type { NextConfig } from "next";

const apiProxyTarget = process.env.API_PROXY_TARGET ?? "http://127.0.0.1:5000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/config", destination: `${apiProxyTarget}/config` },
      { source: "/suggest", destination: `${apiProxyTarget}/suggest` },
      { source: "/search", destination: `${apiProxyTarget}/search` },
      { source: "/health", destination: `${apiProxyTarget}/health` },
    ];
  },
};

export default nextConfig;
