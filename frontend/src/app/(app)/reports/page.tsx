"use client";
import { OperationalOverview } from "@/components/operational-overview";
import { useUser } from "@/components/session";
import { Alert, PageHeader } from "@/components/ui";
import { can } from "@/lib/permissions";

export default function ReportsPage() {
  const user = useUser();
  if (!can.viewOverview(user.role)) return <Alert>You do not have permission to view reports.</Alert>;
  return <div className="mx-auto max-w-content space-y-6 px-4 py-6 sm:px-6"><PageHeader title="Operational reports" eyebrow="Riyadh pilot" /><OperationalOverview /></div>;
}
