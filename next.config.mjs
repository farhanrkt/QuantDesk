/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // In development the Python app runs separately on :8000 (npm run dev:api).
  // In production Vercel routes /api/* to the serverless function via vercel.json,
  // so this rewrite is a no-op there.
  async rewrites() {
    return process.env.NODE_ENV === "development"
      ? [{ source: "/api/:path*", destination: "http://127.0.0.1:8000/api/:path*" }]
      : [];
  },
};
export default nextConfig;
