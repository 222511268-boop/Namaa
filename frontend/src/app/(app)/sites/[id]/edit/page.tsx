"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { RequireRole } from "@/components/app-shell";
import { SiteForm } from "@/components/site-form";
import { Alert, PageHeader, Spinner } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { can } from "@/lib/permissions";
import type { SiteDetail } from "@/lib/types";

export default function EditSitePage() {
  const { id } = useParams<{ id: string }>();
  const [site, setSite] = useState<SiteDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<SiteDetail>(`/api/sites/${id}`).then(setSite).catch((e) => setError(errorMessage(e)));
  }, [id]);

  return (
    <RequireRole allowed={can.editSites}>
      <div className="mx-auto max-w-content px-4 py-6 sm:px-6 sm:py-8">
        <PageHeader title={site ? `Edit ${site.name}` : "Edit green space"} subtitle="Adjust the boundary or update the details." />
        {error && <Alert>{error}</Alert>}
        {!site && !error && <div className="flex justify-center py-16 text-muted"><Spinner className="h-6 w-6" /></div>}
        {site && <SiteForm site={site} />}
      </div>
    </RequireRole>
  );
}
