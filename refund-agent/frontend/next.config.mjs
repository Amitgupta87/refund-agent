/** @type {import('next').NextConfig} */
const nextConfig = {
  // Produces a minimal, self-contained server bundle for the Docker image.
  output: "standalone",
  reactStrictMode: true,
  eslint: {
    // Lint is run separately (npm run lint); don't fail the production build on it.
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
