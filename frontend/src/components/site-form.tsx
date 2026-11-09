"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent, type RefObject } from "react";
import { api, ApiError } from "@/lib/api";
import { PLANTING_LABEL, SITE_TYPE_LABEL } from "@/lib/format";
import type { PlantingCategory, SiteDetail, SiteType } from "@/lib/types";
import { BoundaryEditor } from "./boundary-editor";
import { Alert, Button, Card, ChipGroup, Field, inputClass } from "./ui";

type Geometry = GeoJSON.Polygon | GeoJSON.MultiPolygon;

export type SiteDetails = {
  name: string; nameAr: string; siteType: SiteType | ""; planting: PlantingCategory | ""; notes: string;
  /** Irrigated area in m² (optional; empty means the whole site). */
  irrigated: string;
};

const SITE_TYPES = Object.entries(SITE_TYPE_LABEL).map(([value, label]) => ({ value: value as SiteType, label }));
const PLANTINGS = Object.entries(PLANTING_LABEL)
  .filter(([k]) => k !== "unknown")
  .map(([value, label]) => ({ value: value as PlantingCategory, label }));

// Smart default: a new site starts with the type and planting category last used on this device.
const KIND_KEY = "namaa-last-site-kind";
function lastKind(): { siteType: SiteType | ""; planting: PlantingCategory | "" } {
  try {
    const v = JSON.parse(localStorage.getItem(KIND_KEY) ?? "{}");
    return { siteType: v.siteType ?? "", planting: v.planting ?? "" };
  } catch {
    return { siteType: "", planting: "" };
  }
}
function rememberKind(siteType: string, planting: string) {
  try {
    localStorage.setItem(KIND_KEY, JSON.stringify({ siteType, planting }));
  } catch {
    /* storage unavailable */
  }
}

export function detailsOf(site?: SiteDetail): SiteDetails {
  if (!site) return { name: "", nameAr: "", notes: "", irrigated: "", ...lastKind() };
  return {
    name: site.name,
    nameAr: site.name_ar ?? "",
    siteType: site.site_type,
    planting: site.planting_category !== "unknown" ? site.planting_category : "",
    notes: site.notes ?? "",
    irrigated: site.irrigated_area_m2 ? String(Math.round(site.irrigated_area_m2)) : "",
  };
}

export function validateDetails(d: SiteDetails): Record<string, string> {
  const e: Record<string, string> = {};
  if (!d.name.trim()) e.name = "Enter the green space's name.";
  if (!d.siteType) e.site_type = "Choose a site type.";
  if (!d.planting) e.planting_category = "Choose a planting category.";
  if (d.irrigated.trim() && !(Number(d.irrigated) > 0)) e.irrigated_area_m2 = "Enter the irrigated area in m², or leave it empty.";
  return e;
}

export const detailsBody = (d: SiteDetails) => ({
  name: d.name,
  name_ar: d.nameAr || null,
  site_type: d.siteType,
  planting_category: d.planting,
  notes: d.notes || null,
  irrigated_area_m2: d.irrigated.trim() ? Number(d.irrigated) : null,
});

/** The editable details of a green space; shared by the register form and inline editing on the profile. */
export function SiteDetailsFields({ value, onChange, errors, nameRef, compact = false }: {
  value: SiteDetails; onChange: (v: SiteDetails) => void; errors: Record<string, string>; nameRef?: RefObject<HTMLInputElement | null>; compact?: boolean;
}) {
  // Optional fields stay out of the way until they are needed (or already have content).
  const [more, setMore] = useState(Boolean(value.nameAr || value.notes || value.irrigated));
  const set = (patch: Partial<SiteDetails>) => onChange({ ...value, ...patch });
  const describe = (f: string) => (errors[f] ? `${f}-error` : undefined);
  return (
    <div className="space-y-5">
      <Field label="Name (English)" htmlFor="name" error={errors.name}>
        <input ref={nameRef} id="name" value={value.name} onChange={(e) => set({ name: e.target.value })} maxLength={120}
          className={inputClass(!!errors.name)} aria-invalid={!!errors.name || undefined} aria-describedby={describe("name")} />
      </Field>
      <ChipGroup legend="Site type" name="site_type" value={value.siteType} options={SITE_TYPES}
        onChange={(v) => set({ siteType: v })} error={errors.site_type} />
      <ChipGroup legend="Planting category" name="planting_category" value={value.planting} options={PLANTINGS}
        onChange={(v) => set({ planting: v })} error={errors.planting_category} />
      {more ? (
        <div className={compact ? "grid gap-5 sm:grid-cols-2" : "space-y-5"}>
          <Field label="Name (Arabic, optional)" htmlFor="name_ar" error={errors.name_ar}>
            <input id="name_ar" value={value.nameAr} onChange={(e) => set({ nameAr: e.target.value })} maxLength={120} dir="rtl" lang="ar"
              className={inputClass(!!errors.name_ar)} aria-describedby={describe("name_ar")} />
          </Field>
          <Field label="Notes (optional)" htmlFor="notes" error={errors.notes}>
            <textarea id="notes" rows={compact ? 1 : 3} value={value.notes} onChange={(e) => set({ notes: e.target.value })} maxLength={2000}
              className={inputClass(!!errors.notes)} />
          </Field>
          <Field label="Irrigated area in m² (optional)" htmlFor="irrigated" error={errors.irrigated_area_m2}
            hint="Used for water-demand estimates. Leave empty to use the whole site area.">
            <input id="irrigated" inputMode="decimal" value={value.irrigated} onChange={(e) => set({ irrigated: e.target.value })}
              className={inputClass(!!errors.irrigated_area_m2)} aria-describedby={describe("irrigated_area_m2")} />
          </Field>
        </div>
      ) : (
        <button type="button" onClick={() => setMore(true)} className="text-sm font-medium text-primary-ink underline-offset-4 hover:underline">
          + Arabic name and notes, irrigated area
        </button>
      )}
    </div>
  );
}

export function SiteForm({ site }: { site?: SiteDetail }) {
  const router = useRouter();
  const [details, setDetails] = useState<SiteDetails>(() => detailsOf(site));
  const [geometry, setGeometry] = useState<Geometry | null>(site?.geometry ?? null);
  const [geometryTouched, setGeometryTouched] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const nameRef = useRef<HTMLInputElement>(null);

  async function submit(ev: FormEvent) {
    ev.preventDefault();
    setFormError(null);
    const local = validateDetails(details);
    if (!geometry) local.geometry = "Draw the boundary on the map.";
    setErrors(local);
    if (Object.keys(local).length) return;
    setBusy(true);
    const body = {
      ...detailsBody(details),
      // When editing, only send the boundary if it was changed.
      ...(site && !geometryTouched ? {} : { geometry }),
    };
    try {
      const saved = site
        ? await api<SiteDetail>(`/api/sites/${site.id}`, { method: "PUT", json: body })
        : await api<SiteDetail>("/api/sites", { method: "POST", json: body });
      if (!site) rememberKind(details.siteType, details.planting);
      router.push(`/sites/${saved.id}`);
    } catch (err) {
      setBusy(false);
      if (err instanceof ApiError && Object.keys(err.fieldErrors).length) setErrors(err.fieldErrors);
      else setFormError(err instanceof ApiError ? err.message : "The site could not be saved.");
    }
  }

  return (
    <form onSubmit={submit} noValidate className="grid gap-6 lg:grid-cols-3">
      <Card title="Boundary" className="min-w-0 lg:col-span-2">
        <div className="p-4">
          <BoundaryEditor
            initial={site?.geometry ?? null}
            onChange={(g) => {
              setGeometry(g);
              setGeometryTouched(true);
            }}
            onFinish={() => {
              // Once a new shape is closed, the next thing to do is name it: move focus there (after the map's own click).
              if (!site && !details.name) setTimeout(() => nameRef.current?.focus({ preventScroll: true }), 0);
            }}
            invalid={!!errors.geometry}
            describedBy={errors.geometry ? "geometry-error" : undefined}
          />
          {errors.geometry && <div className="mt-3" id="geometry-error"><Alert>{errors.geometry}</Alert></div>}
        </div>
      </Card>
      <Card title="Details">
        <div className="space-y-5 p-5">
          {formError && <Alert>{formError}</Alert>}
          {site?.needs_review && <Alert tone="info">Imported from OpenStreetMap. Confirm the name and choose a planting category.</Alert>}
          <SiteDetailsFields value={details} onChange={setDetails} errors={errors} nameRef={nameRef} />
          <p className="text-cap text-muted">Area and district are calculated from the boundary. Press Enter in the name field to save.</p>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" busy={busy}>{site ? "Save changes" : "Register green space"}</Button>
            <Button type="button" variant="ghost" onClick={() => router.back()}>Cancel</Button>
          </div>
        </div>
      </Card>
    </form>
  );
}
