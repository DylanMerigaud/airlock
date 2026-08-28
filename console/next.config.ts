import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: __dirname,
  // Mock mode replays this file at request time, so it must ship in the image.
  outputFileTracingIncludes: {
    "/api/run": ["./fixtures/**"],
  },
  eslint: { dirs: ["src"] },
};

export default nextConfig;
