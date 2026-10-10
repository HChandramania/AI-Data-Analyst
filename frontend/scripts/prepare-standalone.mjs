import { cp } from "node:fs/promises";

// Next's standalone server needs its static assets for local production startup.
await cp(".next/static", ".next/standalone/.next/static", { recursive: true });
