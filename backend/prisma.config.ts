import { defineConfig } from "prisma/config";
import * as fs from "fs";

// Prisma 7 evaluates this file before loading .env, so we parse it manually.
// The .env file is expected at backend/.env (same directory as this config).
const raw = fs.readFileSync(".env", "utf-8");
const env: Record<string, string> = {};
for (const line of raw.split("\n")) {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith("#")) continue;
  const idx = trimmed.indexOf("=");
  if (idx === -1) continue;
  env[trimmed.slice(0, idx).trim()] = trimmed.slice(idx + 1).trim();
}

export default defineConfig({
  datasource: {
    url: env.PRISMA_DATABASE_URL,
  },
});
