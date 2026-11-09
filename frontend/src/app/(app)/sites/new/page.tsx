"use client";

import { RequireRole } from "@/components/app-shell";
import { SiteForm } from "@/components/site-form";
import { PageHeader } from "@/components/ui";
import { can } from "@/lib/permissions";

export default function NewSitePage() {
  return (
    <RequireRole allowed={can.editSites}>
      <div className="mx-auto max-w-content px-4 py-6 sm:px-6 sm:py-8">
        <PageHeader title="Register a green space" subtitle="Draw the boundary over the imagery, then add the site's details." />
        <SiteForm />
      </div>
    </RequireRole>
  );
}
