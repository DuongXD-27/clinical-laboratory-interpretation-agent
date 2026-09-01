import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    // React ViewTransition is a progressive enhancement. The CSS motion
    // fallback remains functional in browsers that do not expose the API.
    viewTransition: true,
  },
};

export default nextConfig;
