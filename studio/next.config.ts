import type { NextConfig } from "next";
import { withBotId } from "botid/next/config";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "everything3dindia.com",
        pathname: "/cdn/shop/t/5/assets/render-vs-print-*.png",
      },
    ],
  },
};

// BotID (issue #5): proxies the bot-classification script through our own
// origin so ad-blockers can't strip it. Server checks live in the chat and
// upload routes; protected paths are declared in instrumentation-client.ts.
export default withBotId(nextConfig);
