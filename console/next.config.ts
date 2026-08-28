import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: __dirname,
  eslint: { dirs: ["src"] },
};

export default nextConfig;
