"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useUser } from "@/components/session";
import { SiteMap } from "@/components/site-map";
import { SitePreview } from "@/components/site-preview";
import { Alert, Badge, Button, cx, EmptyState, Icon, inputClass, LinkButton, Segmented, Skeleton } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { formatArea, formatIndex, SITE_TYPE_LABEL, splitSiteName } from "@/lib/format";
import { can } from "@/lib/permissions";
import type { District, SiteSummary } from "@/lib/types";
import { useMediaQuery, WIDE } from "@/lib/use-media";

function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export default function MapPage() {
  const user = useUser();
  const wide = useMediaQuery(WIDE);
  const [view, setView] = useState<"list" | "map">("list");
  const [q, setQ] = useState("");
  const [districtId, setDistrictId] = useState("");
  const [siteType, setSiteType] = useState("");
  const [includeInactive, setIncludeInactive] = useState(false);
  const [districts, setDistricts] = useState<District[]>([]);
  const [sites, setSites] = useState<SiteSummary[] | null>(null);
  const [geo, setGeo] = useState<GeoJSON.FeatureCollection | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [loadedQuery, setLoadedQuery] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const debouncedQ = useDebounced(q);

  useEffect(() => {
    api<District[]>("/api/districts").then(setDistricts).catch(() => undefined);
  }, []);

  const query = useMemo(() => {
    const p = new URLSearchParams();
    if (debouncedQ.trim()) p.set("q", debouncedQ.trim());
    if (districtId) p.set("district_id", districtId);
    if (siteType) p.set("site_type", siteType);
    if (includeInactive) p.set("include_inactive", "true");
    return p.toString();
  }, [debouncedQ, districtId, siteType, includeInactive]);

  useEffect(() => {
    let stale = false;
    Promise.all([
      api<SiteSummary[]>(`/api/sites?${query}`),
      api<GeoJSON.FeatureCollection>(`/api/sites/geojson?${query}`),
    ])
      .then(([list, fc]) => {
        if (stale) return;
        setSites(list);
        setGeo(fc);
        setError(null);
      })
      .catch((e) => !stale && setError(errorMessage(e)))
      .finally(() => !stale && setLoadedQuery(query));
    return () => {
      stale = true;
    };
  }, [query]);

  const loading = loadedQuery !== query;
  const filtered = Boolean(debouncedQ.trim() || districtId || siteType);
  const districtOptions = districts.filter((d) => d.site_count > 0 || String(d.id) === districtId);
  // Phones show one pane at a time; the map (and its JavaScript) loads only when it is asked for.
  const showList = wide || view === "list";
  const showMap = wide || view === "map";

  function clearFilters() {
    setQ("");
    setDistrictId("");
    setSiteType("");
  }

  return (
    <div className="flex h-app flex-col lg:h-screen lg:flex-row">
      <section aria-label="Green-space list"
        className={cx("flex min-h-0 w-full flex-col bg-surface lg:w-panel lg:border-r lg:border-line", showList ? "flex-1 lg:flex-none" : "shrink-0")}>
        <div className="space-y-3 border-b border-line p-4">
          <div className="flex items-center justify-between gap-2">
            <h1 className="text-xl font-semibold tracking-tight text-ink">Green spaces</h1>
            {can.editSites(user.role) && (
              <LinkButton href="/sites/new" size="sm"><Icon name="plus" className="h-4 w-4" />New</LinkButton>
            )}
          </div>
          <div className="lg:hidden">
            <Segmented label="View" value={view} onChange={setView}
              options={[{ value: "list", label: "List", icon: "list" }, { value: "map", label: "Map", icon: "map" }]} />
          </div>
          <div className="relative">
            <label htmlFor="search" className="sr-only">Search by name</label>
            <Icon name="search" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <input id="search" type="search" data-shortcut-search placeholder="Search by name (English or Arabic)   /" value={q}
              onChange={(e) => setQ(e.target.value)} className={cx(inputClass(), "pl-9")} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label htmlFor="district" className="sr-only">District</label>
              <select id="district" value={districtId} onChange={(e) => setDistrictId(e.target.value)} className={inputClass()}>
                <option value="">All districts</option>
                {districtOptions.map((d) => (
                  <option key={d.id} value={d.id}>{d.name_en ?? d.name_ar} ({d.site_count})</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="type" className="sr-only">Site type</label>
              <select id="type" value={siteType} onChange={(e) => setSiteType(e.target.value)} className={inputClass()}>
                <option value="">All types</option>
                {Object.entries(SITE_TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
          </div>
          <div className="flex min-h-6 items-center justify-between text-cap text-muted">
            <span aria-live="polite" data-testid="result-count" className="num">
              {sites ? `${sites.length} ${sites.length === 1 ? "site" : "sites"}` : "Loading…"}
            </span>
            {can.editSites(user.role) && (
              <label className="inline-flex items-center gap-1.5">
                <input type="checkbox" checked={includeInactive} onChange={(e) => setIncludeInactive(e.target.checked)}
                  className="h-4 w-4 accent-primary" />
                Show inactive
              </label>
            )}
          </div>
        </div>

        {showList && (
          <div className={cx("flex-1 overflow-y-auto transition-opacity duration-base", loading && sites && "opacity-60")}>
            {error && <div className="p-4"><Alert>{error}</Alert></div>}
            {!sites && !error && (
              <div className="space-y-px" aria-hidden="true">
                {[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="m-3 h-14" />)}
              </div>
            )}
            {sites && sites.length === 0 && (
              filtered ? (
                <EmptyState icon="search" title="No green spaces match these filters"
                  action={<Button variant="secondary" onClick={clearFilters}>Clear filters</Button>}>
                  Try a different name, district, or site type.
                </EmptyState>
              ) : (
                <EmptyState title="No green spaces yet"
                  action={can.editSites(user.role) ? <LinkButton href="/import">Import from OpenStreetMap</LinkButton> : undefined}>
                  Registered sites will appear here.
                </EmptyState>
              )
            )}
            {sites && sites.length > 0 && (
              <ul className="divide-y divide-line" data-testid="site-list">
                {sites.map((s) => {
                  const { title, ref } = splitSiteName(s.name);
                  return (
                    <li key={s.id} className={cx("group relative flex items-stretch transition-colors duration-fast",
                      preview === s.id ? "bg-primary-soft" : "hover:bg-surface-2")}>
                      {preview === s.id && <span aria-hidden="true" className="absolute inset-y-0 left-0 w-0.5 bg-primary shadow-glow" />}
                      <Link href={`/sites/${s.id}`} data-has-observation={s.latest ? "true" : "false"}
                        onMouseEnter={() => setHovered(s.id)} onMouseLeave={() => setHovered(null)}
                        onFocus={() => setHovered(s.id)} onBlur={() => setHovered(null)}
                        className="flex min-w-0 flex-1 items-start justify-between gap-3 py-3 pl-4 pr-1">
                        <div className="min-w-0">
                          <p className="truncate font-medium text-ink">
                            {title}
                            {ref && <span className="num ml-1.5 text-cap font-normal text-muted">{ref}</span>}
                          </p>
                          {s.name_ar && s.name_ar !== s.name && <p className="truncate text-sm text-ink-2" lang="ar" dir="rtl">{s.name_ar}</p>}
                          <p className="mt-0.5 text-cap text-muted">
                            {SITE_TYPE_LABEL[s.site_type]} · <bdi>{s.district_name ?? "No district"}</bdi> · <span className="num">{formatArea(s.area_m2)}</span>
                            {s.low_confidence && " · Low confidence"}
                          </p>
                          {(s.needs_review || s.status === "inactive") && (
                            <div className="mt-1.5 flex flex-wrap gap-1">
                              {s.status === "inactive" && <Badge>Inactive</Badge>}
                              {s.needs_review && <Badge tone="info">Needs review</Badge>}
                            </div>
                          )}
                        </div>
                        <div className="shrink-0 text-right">
                          <p className="num text-base font-medium text-ink" title="Latest NDVI">{formatIndex(s.latest?.ndvi_mean)}</p>
                          <p className="text-cap text-muted">NDVI</p>
                        </div>
                      </Link>
                      <button type="button" onClick={() => setPreview(preview === s.id ? null : s.id)} aria-pressed={preview === s.id}
                        aria-label={`Preview ${s.name}`} title="Quick preview"
                        className="my-2 mr-2 grid w-10 shrink-0 place-items-center rounded-md text-muted transition hover:bg-surface hover:text-primary-ink hover:shadow-glow aria-pressed:text-primary-ink">
                        <Icon name="eye" className="h-4 w-4" />
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}
      </section>

      {showMap && (
        <SiteMap enableHeat className="min-h-0 flex-1" data={geo} selectedId={hovered ?? preview} fitKey={query} focusId={preview}
          onSelect={setPreview} label="Map of registered green spaces. Select a site for a quick preview; use the list to navigate with a keyboard."
          overlay={wide && preview ? (
            <SitePreview id={preview} role={user.role} onClose={() => setPreview(null)} className="absolute right-3 top-14 w-80 max-w-full" />
          ) : undefined} />
      )}
      {/* Phones: the preview is a bottom sheet over the list or the map. */}
      {!wide && preview && (
        <SitePreview id={preview} role={user.role} onClose={() => setPreview(null)}
          className="fixed inset-x-2 bottom-2 max-h-sheet overflow-y-auto" />
      )}
    </div>
  );
}
