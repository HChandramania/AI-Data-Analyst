import { existsSync } from "node:fs";

// Load server-only local settings before standalone changes its working directory.
process.env.NODE_ENV = "production";
for (const file of [".env.production.local", ".env.local", ".env.production", ".env"]) {
  if (existsSync(file)) process.loadEnvFile(file);
}
await import("../.next/standalone/server.js");
