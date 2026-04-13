import path from "node:path";
import type { NextConfig } from "next";

const projectRoot = path.resolve(__dirname);

const nextConfig: NextConfig = {
  // Pin Turbopack workspace root to this dir (avoids picking up parent
  // lockfiles in $HOME and getting stuck on "Starting...").
  turbopack: {
    root: projectRoot,
  },
  // Next.js 16 exige que outputFileTracingRoot seja igual a turbopack.root
  // pra evitar warning em build.
  outputFileTracingRoot: projectRoot,
};

export default nextConfig;
