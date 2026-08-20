const isDev = process.env.NODE_ENV === "development";

/**
 * Content-Security-Policy.
 *
 * `next/font/google` downloads and self-hosts both faces at build time, so no
 * external font or style origin is needed — `'self'` covers everything the app
 * actually loads, and `connect-src 'self'` keeps the engines' data on our own
 * origin. `'unsafe-inline'` is required for scripts because Next injects inline
 * bootstrap payloads and this app has no nonce plumbing; `'unsafe-eval'` is
 * only added in development, where React Fast Refresh needs it.
 *
 * `frame-ancestors 'none'` is the one that earns its keep: an unauthenticated
 * financial tool is a natural clickjacking frame for an overlay that looks like
 * it belongs to the page.
 */
const csp = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "style-src 'self' 'unsafe-inline'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "connect-src 'self'",
].join("; ");

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
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
          {
            key: "Strict-Transport-Security",
            value: "max-age=63072000; includeSubDomains; preload",
          },
        ],
      },
    ];
  },
};
export default nextConfig;
