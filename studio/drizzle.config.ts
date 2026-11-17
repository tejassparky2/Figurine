import { defineConfig } from "drizzle-kit";
import { loadEnvConfig } from "@next/env";

// Load .env.local the same way Next does, so `npm run db:push` just works.
loadEnvConfig(process.cwd());

export default defineConfig({
  schema: "./lib/db/schema.ts",
  dialect: "postgresql",
  dbCredentials: { url: process.env.DATABASE_URL! },
});
