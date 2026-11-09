"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { RequireRole } from "@/components/app-shell";
import { Alert, Button, Card, Field, inputClass, PageHeader } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { can } from "@/lib/permissions";
import type { District, ImportResult } from "@/lib/types";

// Smart default: the district imported last on this device is preselected.
const DISTRICT_KEY = "namaa-last-import-district";
function lastDistrict(): string {
  try {
    return localStorage.getItem(DISTRICT_KEY) ?? "";
  } catch {
    return "";
  }
}

export default function ImportPage() {
  const [districts, setDistricts] = useState<District[]>([]);
  const [districtId, setDistrictId] = useState(lastDistrict);
  const filterRef = useRef<HTMLInputElement>(null);
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<District[]>("/api/districts").then(setDistricts).catch((e) => setError(errorMessage(e)));
    // Nothing preselected: start typing straight away.
    if (!lastDistrict()) filterRef.current?.focus();
  }, []);

  const onFilter = setFilter;

  const options = useMemo(() => {
    const f = filter.trim().toLowerCase();
    return districts.filter((d) => !f || (d.name_en ?? "").toLowerCase().includes(f) || (d.name_ar ?? "").includes(filter.trim()));
  }, [districts, filter]);

  // Typing a filter picks the first matching district (unless the chosen one still matches), so Enter imports it.
  // Derived rather than stored, so it also works when the district list arrives after typing.
  const selected =
    filter.trim() && !options.some((o) => String(o.id) === districtId) ? String(options[0]?.id ?? "") : districtId;

  async function run(e?: FormEvent) {
    e?.preventDefault();
    if (!selected) {
      setError("Choose a district to import.");
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await api<ImportResult>("/api/imports/osm", { method: "POST", json: { district_id: Number(selected) } });
      setResult(r);
      try {
        localStorage.setItem(DISTRICT_KEY, selected);
      } catch {
        /* storage unavailable */
      }
      api<District[]>("/api/districts").then(setDistricts).catch(() => undefined);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <RequireRole allowed={can.editSites}>
      <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6 sm:py-8">
        <PageHeader title="Import from OpenStreetMap"
          subtitle="Bring in park boundaries mapped by the OpenStreetMap community for one district at a time." />
        <div className="grid gap-6 md:grid-cols-2">
          <Card title="Choose a district">
            <form onSubmit={run} className="space-y-4 p-5">
              <Field label="Filter districts" htmlFor="filter">
                <input ref={filterRef} id="filter" value={filter} onChange={(e) => onFilter(e.target.value)} placeholder="e.g. Rawdah or الروضة" className={inputClass()} />
              </Field>
              <Field label="District" htmlFor="district" hint={`${districts.length} Riyadh districts available`}>
                <select id="district" size={8} value={selected} onChange={(e) => setDistrictId(e.target.value)} className={inputClass()}>
                  {options.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name_en ?? d.name_ar}{d.name_en && d.name_ar ? ` · ${d.name_ar}` : ""}{d.site_count ? ` (${d.site_count} sites)` : ""}
                    </option>
                  ))}
                </select>
              </Field>
              <Button type="submit" busy={busy} disabled={!selected}>{busy ? "Importing… (up to a few minutes if OpenStreetMap is busy)" : "Import parks"}</Button>
              {error && <Alert>{error}</Alert>}
            </form>
          </Card>
          <Card title="What happens">
            <ul className="list-disc space-y-2 py-4 pl-9 pr-5 text-sm text-ink-2">
              <li>Areas tagged as parks inside the district are added as green spaces.</li>
              <li>Parks imported before are skipped, and your edits are never overwritten.</li>
              <li>Features that are not closed areas or have invalid shapes are listed and skipped.</li>
              <li>Imported sites are marked <strong>Needs review</strong> until you confirm the name and planting category.</li>
            </ul>
            <p className="border-t border-line px-5 py-3 text-cap text-muted">Data © OpenStreetMap contributors, available under the Open Database Licence.</p>
          </Card>
        </div>

        {result && (
          <Card title={`Import summary · ${result.district}`} className="mt-6">
            <div className="p-5" data-testid="import-summary">
              <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {[
                  ["Parks found", result.features_found],
                  ["Added", result.created],
                  ["Already imported", result.already_imported],
                  ["Skipped", result.skipped.length],
                ].map(([k, v]) => (
                  <div key={k}>
                    <dt className="text-cap text-muted">{k}</dt>
                    <dd className="num mt-0.5 text-xl font-medium text-ink">{v}</dd>
                  </div>
                ))}
              </dl>
              {result.skipped.length > 0 && (
                <table className="mt-4 w-full text-left text-sm">
                  <caption className="mb-2 text-left text-sm font-medium">Skipped features</caption>
                  <thead className="text-cap text-muted"><tr><th className="py-1.5">OpenStreetMap feature</th><th>Name</th><th>Reason</th></tr></thead>
                  <tbody className="divide-y divide-line">
                    {result.skipped.map((s) => (
                      <tr key={s.osm_ref}>
                        <td className="py-1.5"><a className="text-primary-ink underline underline-offset-4" href={`https://www.openstreetmap.org/${s.osm_ref}`} target="_blank" rel="noopener noreferrer">{s.osm_ref}</a></td>
                        <td>{s.name ?? "—"}</td>
                        <td>{s.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {result.created > 0 && (
                <p className="mt-4 text-sm"><Link href="/map" className="font-medium text-primary-ink underline underline-offset-4">View the new sites on the map →</Link></p>
              )}
            </div>
          </Card>
        )}
      </div>
    </RequireRole>
  );
}
