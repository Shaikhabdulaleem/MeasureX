/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  eslint: {
    // Linting runs through the repo's flat ESLint config (`pnpm lint`), not
    // `next lint`, so skip Next's own lint step during build.
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
