import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pin Turbopack workspace root to this dir (avoids picking up parent
  // lockfiles in $HOME and getting stuck on "Starting...").
  turbopack: {
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
