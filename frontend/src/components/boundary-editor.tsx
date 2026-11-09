"use client";

import type { Map as MlMap } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";
import { loadMaplibre } from "@/lib/maplibre";
import { token, useResolvedTheme } from "@/lib/theme";
import { basemapStyle, RIYADH_CENTER } from "./site-map";
import { Button, cx, Icon, Segmented } from "./ui";

type Geometry = GeoJSON.Polygon | GeoJSON.MultiPolygon;

type Props = {
  initial: Geometry | null;
  onChange: (geometry: Geometry | null) => void;
  onFinish?: () => void; // a shape was just closed by the user
  invalid?: boolean;
  describedBy?: string;
};

/**
 * Draw or edit a site boundary on the map (Terra Draw). Click to add corners and click the first
 * corner (or double-click) to finish. Existing shapes can be reshaped by dragging corners; midpoints
 * add corners. The server validates the final shape (closed, not self-intersecting, inside the pilot area).
 */
export function BoundaryEditor({ initial, onChange, onFinish, invalid, describedBy }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const drawRef = useRef<import("terra-draw").TerraDraw | null>(null);
  const [mode, setMode] = useState<"polygon" | "select">(initial ? "select" : "polygon");
  const [count, setCount] = useState(0);
  const [basemap, setBasemap] = useState<"map" | "imagery">("imagery");
  const [ready, setReady] = useState(false);
  const mapRef = useRef<MlMap | null>(null);
  const theme = useResolvedTheme();
  const themeRef = useRef(theme);
  const onChangeRef = useRef(onChange);
  const onFinishRef = useRef(onFinish);
  useEffect(() => {
    onChangeRef.current = onChange;
    onFinishRef.current = onFinish;
  }, [onChange, onFinish]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [maplibregl, td, { TerraDrawMapLibreGLAdapter }] = await Promise.all([
        loadMaplibre(),
        import("terra-draw"),
        import("terra-draw-maplibre-gl-adapter"),
      ]);
      if (cancelled || !container.current) return;
      const map = new maplibregl.Map({
        container: container.current,
        style: basemapStyle(themeRef.current), // fixed for the editing session; the editor keeps its drawing state
        center: RIYADH_CENTER,
        zoom: 11,
        attributionControl: { compact: true },
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      mapRef.current = map;
      map.on("style.load", () => {
        map.addSource("imagery", {
          type: "raster",
          tiles: ["https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2020_3857/default/g/{z}/{y}/{x}.jpg"],
          tileSize: 256,
          maxzoom: 15,
          attribution: "Sentinel-2 cloudless 2020 by EOX IT Services GmbH (contains modified Copernicus Sentinel data 2020)",
        });
        map.addLayer({ id: "imagery", type: "raster", source: "imagery" });

        const draw = new td.TerraDraw({
          adapter: new TerraDrawMapLibreGLAdapter({ map }),
          modes: [
            new td.TerraDrawPolygonMode({
              validation: (feature, { updateType }) =>
                updateType === "finish" || updateType === "commit" ? td.ValidateNotSelfIntersecting(feature) : { valid: true },
              styles: {
                fillColor: token("--c-ndvi-4") as `#${string}`,
                fillOpacity: 0.35,
                outlineColor: token("--c-map-highlight") as `#${string}`,
                outlineWidth: 2.5,
              },
            }),
            new td.TerraDrawSelectMode({
              flags: {
                polygon: { feature: { draggable: true, coordinates: { midpoints: true, draggable: true, deletable: true } } },
              },
            }),
          ],
        });
        draw.start();

        const emit = () => {
          const polys = draw
            .getSnapshot()
            .filter((f) => f.geometry.type === "Polygon" && !f.properties?.currentlyDrawing)
            .map((f) => (f.geometry as GeoJSON.Polygon).coordinates);
          setCount(polys.length);
          onChangeRef.current(
            polys.length === 0 ? null : polys.length === 1
              ? { type: "Polygon", coordinates: polys[0] }
              : { type: "MultiPolygon", coordinates: polys },
          );
        };
        draw.on("finish", () => {
          emit();
          onFinishRef.current?.();
        });
        draw.on("change", (_ids, type) => {
          if (type !== "styling") emit();
        });

        if (initial) {
          const rings = initial.type === "Polygon" ? [initial.coordinates] : initial.coordinates;
          draw.addFeatures(rings.map((coordinates) => ({
            type: "Feature",
            geometry: { type: "Polygon", coordinates },
            properties: { mode: "polygon" },
          })));
          const flat = rings.flat(2) as unknown as number[][];
          const xs = flat.map((c) => c[0]);
          const ys = flat.map((c) => c[1]);
          map.fitBounds([[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]], { padding: 60, duration: 0, maxZoom: 17 });
          draw.setMode("select");
          emit();
        } else {
          draw.setMode("polygon");
        }
        drawRef.current = draw;
        setReady(true);
      });
    })();
    return () => {
      cancelled = true;
      try { drawRef.current?.stop(); } catch { /* map already removed */ }
      mapRef.current?.remove();
    };
    // The editor is initialised once with the initial geometry.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (drawRef.current?.enabled) drawRef.current.setMode(mode);
  }, [mode]);

  useEffect(() => {
    const map = mapRef.current;
    if (map?.getLayer("imagery")) map.setLayoutProperty("imagery", "visibility", basemap === "imagery" ? "visible" : "none");
  }, [basemap]);

  function clear() {
    drawRef.current?.clear();
    setCount(0);
    onChange(null);
    setMode("polygon");
    drawRef.current?.setMode("polygon");
  }

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Segmented label="Editing tool" value={mode} onChange={setMode}
          options={[{ value: "polygon", label: "Draw shape" }, { value: "select", label: "Adjust corners", disabled: count === 0 }]} />
        <Button type="button" variant="ghost" onClick={clear} disabled={count === 0} size="sm">
          <Icon name="close" className="h-4 w-4" /> Clear
        </Button>
        <span className="ml-auto">
          <Segmented label="Basemap" value={basemap} onChange={setBasemap}
            options={[{ value: "imagery", label: "Imagery" }, { value: "map", label: "Map" }]} />
        </span>
      </div>
      <div
        ref={container}
        className={cx("h-105 overflow-hidden rounded-md bg-surface-2 ring-1", invalid ? "ring-2 ring-danger" : "ring-line")}
        role="application"
        aria-label="Boundary drawing map"
        aria-describedby={describedBy}
        data-testid="boundary-editor"
        data-ready={ready}
      />
      <p className="mt-2 text-cap text-muted">
        {mode === "polygon"
          ? "Click on the map to place each corner. Click the first corner again to close the shape."
          : "Drag a corner to move it, drag a midpoint to add a corner, or right-click a corner to delete it."}
        {" "}{count === 0 ? "No boundary drawn yet." : `${count} ${count === 1 ? "shape" : "shapes"} drawn.`}
      </p>
    </div>
  );
}
