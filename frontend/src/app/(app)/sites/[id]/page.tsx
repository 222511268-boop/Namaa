"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { rememberSite } from "@/components/command-palette";
import { ConditionChart } from "@/components/condition-chart";
import { useUser } from "@/components/session";
import { detailsBody, detailsOf, SiteDetailsFields, validateDetails, type SiteDetails } from "@/components/site-form";
import { SiteMap } from "@/components/site-map";
import { useToast } from "@/components/toast";
import { HeatCard } from "@/components/heat-card";
import { WaterCard } from "@/components/water-card";
import { Alert, Badge, Button, Card, EmptyState, Icon, LinkButton, Menu, Skeleton, type MenuItem } from "@/components/ui";
import { api, ApiError, errorMessage } from "@/lib/api";
import { formatArea, formatDate, formatDateTime, formatIndex, percent, PLANTING_LABEL, SITE_TYPE_LABEL, splitSiteName } from "@/lib/format";
import { smartRange, startRun } from "@/lib/live-runs";
import { can } from "@/lib/permissions";
import type { Baseline, ConditionHistory, SiteDetail, TimelineEvent } from "@/lib/types";

export default function SiteProfilePage() {
  const { id } = useParams<{ id: string }>();
  const user = useUser();
  const [site, setSite] = useState<SiteDetail | null>(null);
  const [history, setHistory] = useState<ConditionHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [baselines, setBaselines] = useState<Baseline[]>([]);
  const [timeline, setTimeline] = useState<{ active_signal_id: string | null; events: TimelineEvent[] } | null>(null);
  const [editing, setEditing] = useState(false);
  const toast = useToast();

  const load = useCallback(() => {
    Promise.all([
      api<SiteDetail>(`/api/sites/${id}`),
      api<ConditionHistory>(`/api/sites/${id}/observations`),
      api<Baseline[]>(`/api/sites/${id}/baselines`),
      api<{ active_signal_id: string | null; events: TimelineEvent[] }>(`/api/sites/${id}/timeline`),
    ])
      .then(([s, h, b, t]) => {
        rememberSite({ id: s.id, name: s.name });
        setSite(s);
        setHistory(h);
        setBaselines(b);
        setTimeline(t);
      })
      .catch((e) => (e instanceof ApiError && (e.status === 404 || e.status === 422) ? setNotFound(true) : setError(errorMessage(e))));
  }, [id]);
  useEffect(load, [load]);

  const fc = useMemo<GeoJSON.FeatureCollection | null>(
    () =>
      site && {
        type: "FeatureCollection",
        features: [{ type: "Feature", geometry: site.geometry, properties: { id: site.id, ndvi: site.latest?.ndvi_mean ?? null, low_confidence: site.low_confidence } }],
      },
    [site],
  );

  async function updateThisSite() {
    if (!site || !history) return;
    const range = smartRange(history.latest_usable_on);
    try {
      await startRun(range, [site.id]);
      toast({ tone: "info", text: `Run queued for this site (${range.start} to ${range.end}).`, href: "/processing", action: "Follow" });
    } catch (e) {
      toast({ tone: "danger", text: errorMessage(e) });
    }
  }

  async function toggleStatus() {
    if (!site) return;
    try {
      setSite(await api<SiteDetail>(`/api/sites/${site.id}/status`, {
        method: "PATCH",
        json: { status: site.status === "active" ? "inactive" : "active" },
      }));
      toast({ tone: "success", text: site.status === "active" ? "Green space deactivated." : "Green space reactivated." });
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  if (notFound)
    return (
      <div className="p-8">
        <EmptyState icon="search" title="Green space not found" action={<LinkButton href="/map" variant="secondary">Back to green spaces</LinkButton>}>
          It may have been removed, or the link is incorrect.
        </EmptyState>
      </div>
    );
  if (error && !site) return <div className="p-8"><Alert>{error}</Alert></div>;
  if (!site || !history)
    return (
      <div className="mx-auto max-w-content space-y-4 px-4 py-6 sm:px-6" aria-busy="true" aria-label="Loading green space">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-9 w-72 max-w-full" />
        <Skeleton className="h-96" />
      </div>
    );
  const { title, ref } = splitSiteName(site.name);

  return (
    <div className="mx-auto max-w-content px-4 py-6 sm:px-6">
      <Link href="/map" className="mb-4 inline-flex min-h-9 items-center gap-1 text-sm font-medium text-primary-ink hover:underline">
        <Icon name="back" className="h-4 w-4" /> Green spaces
      </Link>
      {editing ? (
        <InlineEditor site={site} onCancel={() => setEditing(false)}
          onSaved={(saved) => { setSite(saved); setEditing(false); toast({ tone: "success", text: "Details saved." }); }} />
      ) : (
        <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl" data-testid="site-name">
              {title}{ref && <>{" "}<span className="num align-middle text-sm font-normal text-muted">{ref}</span></>}
            </h1>
            {site.name_ar && site.name_ar !== site.name && <p className="mt-0.5 text-lg text-ink-2" lang="ar" dir="rtl">{site.name_ar}</p>}
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Badge>{SITE_TYPE_LABEL[site.site_type]}</Badge>
              {site.status === "inactive" && <Badge tone="danger">Inactive</Badge>}
              {site.needs_review && <Badge tone="info" title="Imported from OpenStreetMap; confirm the name and planting category">Needs review</Badge>}
              {site.low_confidence && (
                <Badge tone="warn" title="Smaller than the minimum monitoring size; satellite values mix in surrounding surfaces">
                  <Icon name="alert" className="h-3 w-3" /> Low confidence
                </Badge>
              )}
            </div>
            <Link href={`/sites/${site.id}/report`} className="mt-3 inline-flex min-h-9 items-center gap-1.5 text-sm font-medium text-primary-ink hover:underline" data-testid="site-report-link">
              <Icon name="print" className="h-4 w-4" /> Printable report
            </Link>
          </div>
          {can.editSites(user.role) && (
            <div className="flex flex-wrap gap-2">
              {/* One primary action: reviewing imported details when needed, otherwise creating a task. */}
              <Button variant={site.needs_review ? "primary" : "secondary"} onClick={() => setEditing(true)}>
                <Icon name="edit" className="h-4 w-4" />{site.needs_review ? "Review details" : "Edit details"}
              </Button>
              <LinkButton href={`/tasks/new?site=${site.id}`} variant={site.needs_review ? "secondary" : "primary"}>
                <Icon name="clipboard" className="h-4 w-4" />Create task
              </LinkButton>
              <Menu label="More actions" icon="more" items={[
                { label: "Edit boundary", icon: "map", href: `/sites/${site.id}/edit` },
                ...(can.runProcessing(user.role) && site.status === "active"
                  ? [{ label: "Update satellite data for this site", icon: "satellite", onSelect: updateThisSite } satisfies MenuItem]
                  : []),
                site.status === "active"
                  ? { label: "Deactivate", icon: "close", tone: "danger", onSelect: toggleStatus } satisfies MenuItem
                  : { label: "Reactivate", icon: "refresh", onSelect: toggleStatus } satisfies MenuItem,
              ]} />
            </div>
          )}
        </div>
      )}
      {error && <div className="mb-4"><Alert>{error}</Alert></div>}
      {timeline?.active_signal_id && (
        <div className="mb-4" data-testid="active-signal-banner">
          <Alert tone="signal">
            This site has an active vegetation-decline signal.{" "}
            {can.viewSignals(user.role) ? (
              <Link href={`/signals/${timeline.active_signal_id}`} className="font-medium underline">Review the evidence</Link>
            ) : "A manager is reviewing it."}
          </Alert>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card
          className="min-w-0 lg:col-span-2"
          title="Condition history"
          action={<Badge tone="info" title="Values are calculated from Sentinel-2 satellite imagery">Satellite-derived</Badge>}
        >
          <div className="px-4 py-4 sm:px-5">
            <dl className="mb-5 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4" data-testid="data-quality">
              <Quality label="Latest NDVI" value={formatIndex(site.latest?.ndvi_mean)} />
              <Quality label="Latest image" value={formatDate(history.latest_usable_on)} />
              <Quality label="Usable observations" value={String(history.usable_count)} />
              <Quality label="Not used (cloud)" value={String(history.unusable_count)} />
            </dl>
            {history.usable_count > 0 ? (
              <>
                <ConditionChart observations={history.observations} baselines={baselines} />
                <BaselineNote baselines={baselines} lowConfidence={site.low_confidence} />
              </>
            ) : (
              <div data-testid="no-observations">
                <EmptyState icon="satellite" title="No usable satellite observations yet"
                  action={can.runProcessing(user.role) ? <LinkButton href="/processing" variant="secondary">Update satellite data</LinkButton> : undefined}>
                  {history.unusable_count > 0
                    ? `${history.unusable_count} images were found but too cloudy or shadowed over this site.`
                    : "Satellite data has not been processed for this site yet."}
                </EmptyState>
              </div>
            )}
            {history.attribution && (
              <p className="mt-3 text-cap text-muted">Sentinel-2 Level-2A · <span data-testid="s2-attribution">{history.attribution}</span></p>
            )}
            <details className="mt-4 rounded-md bg-surface-2 px-4 py-3 text-sm">
              <summary className="cursor-pointer font-medium text-ink">What do NDVI and NDMI mean?</summary>
              <div className="mt-2 space-y-2 text-ink-2">
                <p><strong>NDVI (Normalised Difference Vegetation Index)</strong> compares red and near-infrared light. Dense, green
                  vegetation reflects much more near-infrared, so it scores higher (often 0.4–0.8); bare soil and paving score near 0.</p>
                <p><strong>NDMI (Normalised Difference Moisture Index)</strong> compares near-infrared and short-wave infrared light, which
                  is absorbed by water. Higher values suggest more moisture in the leaves.</p>
                <p className="rounded-md bg-warn-soft px-3 py-2 text-warn-ink">
                  <strong>Greenness is not the same as health.</strong> Drought-adapted and native planting can be healthy with low values.
                  Compare a site with its own history, and confirm concerns in the field.
                </p>
                <p>Each value is the average of the 10 m pixels whose centre lies inside the site boundary. An image is used when at least{" "}
                  {percent(history.thresholds.min_valid_share)} of those pixels are clear (and at least {history.thresholds.min_valid_pixels} pixels).</p>
              </div>
            </details>
          </div>
        </Card>

        <div className="min-w-0 space-y-6">
          <Card className="overflow-hidden">
            <SiteMap data={fc} fitKey={site.id + site.updated_at} className="h-64" showLegend={false} lazy label={`Boundary of ${site.name}`} />
          </Card>
          <Card title="Details">
            <dl className="divide-y divide-line text-sm">
              <Row label="Planting" value={PLANTING_LABEL[site.planting_category]} />
              <Row label="District" value={site.district_name ?? "Outside mapped districts"} />
              <Row label="Area" value={formatArea(site.area_m2)} />
              <Row label="Boundary source" value={site.source === "osm" ? `OpenStreetMap (${site.source_ref})` : "Drawn in Namaa"} />
              <Row label="Last updated" value={formatDate(site.updated_at)} />
              {site.notes && <Row label="Notes" value={site.notes} />}
            </dl>
            {site.source_attribution && <p className="border-t border-line px-5 py-2.5 text-cap text-muted">{site.source_attribution}</p>}
          </Card>
          <Card title="Activity">
            {!timeline || timeline.events.length === 0 ? (
              <p className="px-5 py-4 text-sm text-muted">No signals or tasks yet.</p>
            ) : (
              <ol className="relative space-y-4 px-5 pb-5 pt-3 text-sm" data-testid="site-timeline">
                {timeline.events.map((e, i) => (
                  <li key={i} className="relative border-s-2 border-line ps-4">
                    <span className="absolute -start-1.25 top-1.5 h-2 w-2 rounded-full bg-primary" aria-hidden="true" />
                    <p className="font-medium text-ink">
                      {e.task_id ? <Link href={`/tasks/${e.task_id}`} className="hover:underline">{e.text}</Link>
                        : e.signal_id && can.viewSignals(user.role) ? <Link href={`/signals/${e.signal_id}`} className="hover:underline">{e.text}</Link>
                        : e.text}
                    </p>
                    {e.detail && <p className="text-ink-2">{e.detail}</p>}
                    <p className="text-cap text-muted">{formatDateTime(e.at)}{e.user ? ` · ${e.user}` : ""}</p>
                  </li>
                ))}
              </ol>
            )}
          </Card>
        </div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="min-w-0 lg:col-span-2"><WaterCard siteId={site.id} canEdit={can.editSites(user.role)} /></div>
        <div className="min-w-0"><HeatCard siteId={site.id} canProcess={can.runProcessing(user.role)} /></div>
      </div>
    </div>
  );
}

function Quality({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-cap text-muted">{label}</dt>
      <dd className="num mt-0.5 text-lg font-medium text-ink">{value}</dd>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 px-5 py-2.5">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right text-ink"><bdi>{value}</bdi></dd>
    </div>
  );
}

function BaselineNote({ baselines, lowConfidence }: { baselines: Baseline[]; lowConfidence: boolean }) {
  const available = baselines.filter((b) => b.available);
  if (lowConfidence)
    return <p className="mt-2 text-cap text-muted" data-testid="baseline-note">Below the monitoring size: this site is not checked for unusual decline.</p>;
  if (baselines.length === 0 || available.length === 0)
    return (
      <p className="mt-2 text-cap text-muted" data-testid="baseline-note">
        Seasonal baseline not available yet: at least 8 observations from an earlier year are needed for each season.
      </p>
    );
  const counts = available.map((b) => b.n_obs);
  return (
    <p className="mt-2 text-cap text-muted" data-testid="baseline-note">
      Seasonal baseline for {available[0].target_year} from {available[0].years} data: {available.length} of 12 months available,
      each from {Math.min(...counts)}–{Math.max(...counts)} observations in the same three-month season.
    </p>
  );
}

/** Inline editing of a site's details on the profile (the boundary keeps its own editor). Enter saves, Esc cancels. */
function InlineEditor({ site, onCancel, onSaved }: { site: SiteDetail; onCancel: () => void; onSaved: (s: SiteDetail) => void }) {
  const [details, setDetails] = useState<SiteDetails>(() => detailsOf(site));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const nameRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    nameRef.current?.focus();
    nameRef.current?.select();
  }, []);

  async function save(e: FormEvent) {
    e.preventDefault();
    const local = validateDetails(details);
    setErrors(local);
    if (Object.keys(local).length) return;
    setBusy(true);
    try {
      onSaved(await api<SiteDetail>(`/api/sites/${site.id}`, { method: "PUT", json: detailsBody(details) }));
    } catch (err) {
      setBusy(false);
      setErrors(err instanceof ApiError && Object.keys(err.fieldErrors).length ? err.fieldErrors : { form: errorMessage(err) });
    }
  }

  return (
    <form onSubmit={save} noValidate onKeyDown={(e) => e.key === "Escape" && onCancel()} data-testid="inline-editor"
      className="mb-8 animate-fade-in rounded-lg bg-surface p-5 shadow-glow ring-1 ring-primary/30 sm:p-6">
      <p className="mb-4 text-cap font-medium text-primary-ink">Editing details · Enter saves · Esc cancels</p>
      {errors.form && <div className="mb-4"><Alert>{errors.form}</Alert></div>}
      <SiteDetailsFields value={details} onChange={setDetails} errors={errors} nameRef={nameRef} compact />
      <div className="mt-5 flex flex-wrap gap-2">
        <Button type="submit" busy={busy}>Save changes</Button>
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  );
}
