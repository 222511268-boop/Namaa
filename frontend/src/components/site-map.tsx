"use client";

import type { GeoJSONSource, Map as MlMap, MapLayerMouseEvent } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";
import { loadMaplibre } from "@/lib/maplibre";
import { api, errorMessage } from "@/lib/api";
import type { HeatLayers } from "@/lib/types";
import { token, useResolvedTheme } from "@/lib/theme";
import { formatIndex, splitSiteName } from "@/lib/format";
import { cx, Segmented, inputClass } from "./ui";

export const RIYADH_CENTER: [number, number] = [46.72, 24.72];

// One-hue sequential ramp for latest NDVI (light = low, dark = high); colours are the --c-ndvi-1..5 tokens.
// Grey (--c-ndvi-none) = no satellite data yet.
const NDVI_STEPS: { min: number; token: string; label: string }[] = [
  { min: -1, token: "--c-ndvi-1", label: "< 0.10" },
  { min: 0.1, token: "--c-ndvi-2", label: "0.10–0.20" },
  { min: 0.2, token: "--c-ndvi-3", label: "0.20–0.30" },
  { min: 0.3, token: "--c-ndvi-4", label: "0.30–0.45" },
  { min: 0.45, token: "--c-ndvi-5", label: "≥ 0.45" },
];

/** OpenFreeMap vector styles: a quiet light basemap, and its dark counterpart for dark mode. */
export const basemapStyle = (theme: "light" | "dark") => `https://tiles.openfreemap.org/styles/${theme === "dark" ? "dark" : "positron"}`;

const IMAGERY_ATTRIBUTION =
  '<a href="https://s2maps.eu" target="_blank" rel="noopener">Sentinel-2 cloudless 2020</a> by EOX IT Services GmbH ' +
  "(contains modified Copernicus Sentinel data 2020)";

function fillColorExpression(): unknown {
  const steps: unknown[] = ["step", ["get", "ndvi"], token(NDVI_STEPS[0].token)];
  for (const s of NDVI_STEPS.slice(1)) steps.push(s.min, token(s.token));
  return ["case", ["==", ["get", "ndvi"], null], token("--c-ndvi-none"), steps];
}

type Props = {
  data: GeoJSON.FeatureCollection | null;
  selectedId?: string | null;
  onSelect?: (id: string) => void;
  fitKey?: string; // changes when the map should re-fit to the data (e.g. filters changed)
  className?: string;
  interactive?: boolean;
  showLegend?: boolean;
  label: string;
  lazy?: boolean; // load MapLibre only once the map is in view and the browser is idle (secondary maps)
  focusId?: string | null; // fly to this site (e.g. when its preview opens)
  overlay?: React.ReactNode; // floating panels drawn over the map (preview)
  enableHeat?: boolean;
};

type Hover = { x: number; y: number; name: string; ndvi: number | null };

export function SiteMap({ data, selectedId, onSelect, fitKey, className, interactive = true, showLegend = true, label, lazy = false, focusId, overlay, enableHeat = false }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const [inView, setInView] = useState(!lazy);
  const mapRef = useRef<MlMap | null>(null);
  const theme = useResolvedTheme();
  const [ready, setReady] = useState(false);
  const [basemap, setBasemap] = useState<"map" | "imagery">("map");
  const [narrow, setNarrow] = useState(false);
  const [hover, setHover] = useState<Hover | null>(null);
  const [heat, setHeat] = useState<HeatLayers | null>(null);
  const [heatDate, setHeatDate] = useState("");
  const [heatError, setHeatError] = useState<string | null>(null);
  useEffect(() => {
    if (!enableHeat) return;
    let stale = false;
    api<HeatLayers>("/api/heat/layers?limit=50").then(h => { if (!stale) setHeat(h); }).catch(e => { if (!stale) setHeatError(errorMessage(e)); });
    return () => { stale = true; };
  }, [enableHeat]);
  const onSelectRef = useRef(onSelect);
  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    if (inView || !container.current) return;
    // Secondary maps start once visible and the main thread is idle, so the page's primary content renders first.
    let idle: number | undefined;
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting || idle !== undefined) return;
      idle = window.requestIdleCallback(() => setInView(true), { timeout: 2000 });
    }, { rootMargin: "200px" });
    io.observe(container.current);
    return () => {
      io.disconnect();
      if (idle !== undefined) window.cancelIdleCallback(idle);
    };
  }, [inView]);

  // Create the map; recreated when the theme changes so basemap and data colours follow the tokens.
  useEffect(() => {
    if (!inView) return;
    let cancelled = false;
    let observer: ResizeObserver | undefined;
    (async () => {
      const maplibregl = await loadMaplibre();
      if (cancelled || !container.current) return;
      const map = new maplibregl.Map({
        container: container.current,
        style: basemapStyle(theme),
        center: RIYADH_CENTER,
        zoom: 10.5,
        interactive,
        attributionControl: { compact: true },
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      // Keep the canvas matched to its box (e.g. after a mobile List/Map switch or a sidebar change).
      observer = new ResizeObserver(() => map.resize());
      observer.observe(container.current);
      map.on("load", () => {
        const outline = token("--c-map-outline");
        map.addSource("imagery", {
          type: "raster",
          tiles: ["https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2020_3857/default/g/{z}/{y}/{x}.jpg"],
          tileSize: 256,
          maxzoom: 15,
          attribution: IMAGERY_ATTRIBUTION,
        });
        map.addLayer({ id: "imagery", type: "raster", source: "imagery", layout: { visibility: "none" } });
        map.addSource("sites", { type: "geojson", data: { type: "FeatureCollection", features: [] }, promoteId: "id" });
        map.addLayer({
          id: "sites-fill",
          type: "fill",
          source: "sites",
          paint: { "fill-color": fillColorExpression() as never, "fill-opacity": 0.8 },
        });
        map.addLayer({
          id: "sites-line",
          type: "line",
          source: "sites",
          filter: ["!=", ["get", "low_confidence"], true],
          paint: { "line-color": outline, "line-width": 1.2 },
        });
        map.addLayer({
          id: "sites-line-low",
          type: "line",
          source: "sites",
          filter: ["==", ["get", "low_confidence"], true],
          paint: { "line-color": outline, "line-width": 1.2, "line-dasharray": [2, 1.5] },
        });
        // Selection glow: a soft, wide, blurred line under the crisp highlight.
        map.addLayer({
          id: "sites-selected-glow",
          type: "line",
          source: "sites",
          filter: ["==", ["get", "id"], ""],
          paint: { "line-color": token("--c-map-highlight"), "line-width": 12, "line-blur": 8, "line-opacity": 0.45 },
        });
        map.addLayer({
          id: "sites-selected",
          type: "line",
          source: "sites",
          filter: ["==", ["get", "id"], ""],
          paint: { "line-color": token("--c-map-highlight"), "line-width": 3.5 },
        });
        if (interactive) {
          map.on("click", "sites-fill", (e: MapLayerMouseEvent) => {
            const id = e.features?.[0]?.properties?.id;
            if (id) onSelectRef.current?.(String(id));
          });
          map.on("mouseenter", "sites-fill", () => (map.getCanvas().style.cursor = "pointer"));
          map.on("mousemove", "sites-fill", (e: MapLayerMouseEvent) => {
            const p = e.features?.[0]?.properties;
            if (p) setHover({ x: e.point.x, y: e.point.y, name: String(p.name ?? ""), ndvi: p.ndvi === null || p.ndvi === undefined || p.ndvi === "null" ? null : Number(p.ndvi) });
          });
          map.on("mouseleave", "sites-fill", () => {
            map.getCanvas().style.cursor = "";
            setHover(null);
          });
        }
        // On small maps the expanded attribution and legend would cover the data; keep them one tap away.
        if (container.current && container.current.clientWidth < 640) {
          const attrib = container.current.querySelector(".maplibregl-ctrl-attrib");
          attrib?.classList.remove("maplibregl-compact-show");
          attrib?.removeAttribute("open");
          setNarrow(true);
        }
        mapRef.current = map;
        setReady(true);
      });
    })();
    return () => {
      cancelled = true;
      observer?.disconnect();
      mapRef.current?.remove();
      mapRef.current = null;
      setReady(false);
    };
  }, [interactive, theme, inView]);

  // Update data.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !data) return;
    (map.getSource("sites") as GeoJSONSource).setData(data);
  }, [ready, data]);

  // Fit to the data when the fit key changes.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !data || data.features.length === 0) return;
    let minX = 180, minY = 90, maxX = -180, maxY = -90;
    const visit = (c: unknown): void => {
      if (Array.isArray(c) && typeof c[0] === "number") {
        minX = Math.min(minX, c[0]); maxX = Math.max(maxX, c[0]);
        minY = Math.min(minY, c[1] as number); maxY = Math.max(maxY, c[1] as number);
      } else if (Array.isArray(c)) c.forEach(visit);
    };
    data.features.forEach((f) => visit((f.geometry as GeoJSON.Polygon).coordinates));
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    map.fitBounds([[minX, minY], [maxX, maxY]], { padding: 48, maxZoom: 16, duration: reduce ? 0 : 600 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, fitKey]);

  // Highlight the selected site.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.setFilter("sites-selected", ["==", ["get", "id"], selectedId ?? ""]);
    map.setFilter("sites-selected-glow", ["==", ["get", "id"], selectedId ?? ""]);
  }, [ready, selectedId]);

  // Fly to a focused site (smooth; instant under reduced motion).
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !data || !focusId) return;
    const f = data.features.find((ft) => ft.properties?.id === focusId);
    if (!f) return;
    let minX = 180, minY = 90, maxX = -180, maxY = -90;
    const visit = (c: unknown): void => {
      if (Array.isArray(c) && typeof c[0] === "number") {
        minX = Math.min(minX, c[0]); maxX = Math.max(maxX, c[0]);
        minY = Math.min(minY, c[1] as number); maxY = Math.max(maxY, c[1] as number);
      } else if (Array.isArray(c)) c.forEach(visit);
    };
    visit((f.geometry as GeoJSON.Polygon).coordinates);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const wide = (container.current?.clientWidth ?? 0) >= 640;
    map.fitBounds([[minX, minY], [maxX, maxY]], {
      padding: wide ? { top: 80, bottom: 80, left: 80, right: 380 } : 60,
      maxZoom: 16.5,
      duration: reduce ? 0 : 700,
    });
  }, [ready, focusId, data]);

  // Basemap toggle.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.setLayoutProperty("imagery", "visibility", basemap === "imagery" ? "visible" : "none");
    map.setPaintProperty("sites-fill", "fill-opacity", heatDate ? 0.05 : basemap === "imagery" ? 0.55 : 0.8);
  }, [ready, basemap, heatDate]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !heat) return;
    const ids: string[] = [];
    // All footprints from the chosen acquisition date are rendered, including adjacent scenes.
    for (const layer of heat.layers.filter(l => l.acquired_on === heatDate)) {
      const id = `heat-${layer.id}`;
      const [w, s, e, n] = layer.bounds;
      map.addSource(id, { type: "image", url: layer.url, coordinates: [[w, n], [e, n], [e, s], [w, s]] });
      map.addLayer({ id, type: "raster", source: id, paint: { "raster-opacity": 0.85, "raster-resampling": "nearest", "raster-fade-duration": 0 } }, "sites-fill");
      ids.push(id);
    }
    return () => {
      if (mapRef.current !== map) return;
      for (const id of ids) { if (map.getLayer(id)) map.removeLayer(id); if (map.getSource(id)) map.removeSource(id); }
    };
  }, [ready, heat, heatDate]);

  return (
    <div className={cx("relative overflow-hidden bg-surface-2", className)}>
      {/* Inline position: maplibre-gl.css (unlayered) sets .maplibregl-map { position: relative }, which would
          override a Tailwind "absolute" utility and collapse the container to zero height. */}
      <div ref={container} style={{ position: "absolute", inset: 0 }} role="region" aria-label={label} data-testid="site-map" data-ready={ready} />
      <div className="glass absolute left-3 top-3 max-w-64 space-y-2 rounded-md p-0.5">
        <Segmented label="Basemap" value={basemap} onChange={setBasemap}
          options={[{ value: "map", label: "Map" }, { value: "imagery", label: "Imagery" }]} />
        {enableHeat && <div className="px-2 pb-2 text-cap">
          <label htmlFor="map-heat-date" className="mb-1 block font-medium">Surface heat layer</label>
          <select id="map-heat-date" className={inputClass()} value={heatDate} onChange={e => setHeatDate(e.target.value)}>
            <option value="">Off · show NDVI</option>
            {[...new Set((heat?.layers ?? []).map(l => l.acquired_on))].map(d => <option key={d} value={d}>Landsat · {d}</option>)}
          </select>
          {heat && !heat.layers.length && <p className="mt-1 text-muted">No processed Landsat layers available.</p>}
          {heatError && <p role="alert">{heatError}</p>}
        </div>}
      </div>
      {showLegend && ready && !heatDate && <NdviLegend defaultOpen={!narrow} />}
      {heatDate && heat && <details open={!narrow} className="glass absolute bottom-3 left-3 max-w-64 rounded-md p-3 text-cap">
        <summary className="cursor-pointer font-medium">Land surface temperature (°C)</summary>
        <p className="my-1">Acquired {heatDate} · Satellite-derived</p>
        <ul>{heat.ramp.map(r => <li key={r.c} className="flex items-center gap-2"><span className="h-3 w-5" style={{ background: r.color }} />{r.c} °C</li>)}</ul>
        <p className="mt-2">{heat.resolution}</p><p>{heat.attribution}. Transparent pixels have no usable data.</p>
      </details>}
      {hover && (
        <div aria-hidden="true" className="glass pointer-events-none absolute left-0 top-0 z-10 rounded-md px-2.5 py-1.5 text-cap"
          style={{ transform: `translate(${hover.x + 14}px, ${hover.y + 14}px)` }}>
          <span className="block max-w-56 truncate font-medium text-ink">{splitSiteName(hover.name).title}</span>
          <span className="num text-muted">NDVI {formatIndex(hover.ndvi)}</span>
        </div>
      )}
      {overlay}
    </div>
  );
}

function NdviLegend({ defaultOpen = true }: { defaultOpen?: boolean }) {
  return (
    <details open={defaultOpen}
      className="glass absolute bottom-3 left-3 max-w-56 rounded-md px-3 py-2 text-cap">
      <summary className="cursor-pointer font-medium text-ink">Latest NDVI</summary>
      <ul className="mt-1.5 space-y-1">
        {NDVI_STEPS.slice().reverse().map((s) => (
          <li key={s.label} className="flex items-center gap-2 text-ink-2">
            <span className="h-3 w-5 rounded-sm ring-1 ring-line ring-inset" style={{ background: `var(${s.token})` }} />
            <span className="num">{s.label}</span>
          </li>
        ))}
        <li className="flex items-center gap-2 text-ink-2">
          <span className="h-3 w-5 rounded-sm ring-1 ring-line ring-inset" style={{ background: "var(--c-ndvi-none)" }} />No data yet
        </li>
        <li className="flex items-center gap-2 text-ink-2">
          <span className="h-0 w-5 border-t-2 border-dashed" style={{ borderColor: "var(--c-map-outline)" }} />Below monitoring size
        </li>
      </ul>
    </details>
  );
}
