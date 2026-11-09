// MapLibre GL runs tile parsing in a Web Worker that it loads by URL. Bundlers do not emit that
// file, so it is copied into public/ before dev and build, and selected with setWorkerUrl().
import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";

const require = createRequire(import.meta.url);
const dist = dirname(require.resolve("maplibre-gl/package.json"));
mkdirSync("public/vendor", { recursive: true });
copyFileSync(join(dist, "dist", "maplibre-gl-worker.mjs"), join("public", "vendor", "maplibre-gl-worker.mjs"));
console.log("Copied maplibre-gl-worker.mjs to public/vendor/");
