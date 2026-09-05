const isDevelopment = process.env.NODE_ENV !== "production";

/** @type {import("next").NextConfig} */
const nextConfig = {
  // Keep the dev watcher isolated from production builds. Sharing .next lets
  // concurrent commands remove chunks that the other process is serving.
  distDir: isDevelopment ? ".next-dev" : ".next",
};

export default nextConfig;
