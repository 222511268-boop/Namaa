/** Load MapLibre on the client and point it at the worker served from /vendor (see scripts/copy-maplibre-worker.mjs). */
export async function loadMaplibre() {
  const maplibregl = await import("maplibre-gl");
  if (!maplibregl.getWorkerUrl().includes("/vendor/")) {
    maplibregl.setWorkerUrl(`/vendor/maplibre-gl-worker.mjs?v=${maplibregl.getVersion()}`);
  }
  return maplibregl;
}
