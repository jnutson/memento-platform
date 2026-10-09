const apiOrigin = process.env.MEMENTO_API_ORIGIN ?? "http://127.0.0.1:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  allowedDevOrigins: ["127.0.0.1"],
  async rewrites() {
    return [
      { source: "/api/healthz", destination: `${apiOrigin}/healthz` },
      { source: "/api/attention", destination: `${apiOrigin}/v1/attention` },
      { source: "/api/attention/:predictionId", destination: `${apiOrigin}/v1/attention/:predictionId` },
      { source: "/api/signals", destination: `${apiOrigin}/v1/signals` },
      { source: "/api/signals/:signalId", destination: `${apiOrigin}/v1/signals/:signalId` },
    ];
  },
};

export default nextConfig;
