"use client";

import { useEffect, useState } from "react";
import {
  ApplicationEnvironment,
  ApplicationInventoryItem,
  fetchApplications,
} from "@/app/utils/applicationsApi";

interface ApplicationsTabProps {
  token: string;
}

function InventoryValue({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] font-mono uppercase tracking-[0.18em] text-muted-sem">{label}</dt>
      <dd className="mt-1 break-all font-mono text-xs text-foreground-sem">{value || "Not recorded"}</dd>
    </div>
  );
}

function EnvironmentCard({ environment }: { environment: ApplicationEnvironment }) {
  const production = environment.environment_key === "production";
  return (
    <section
      className={`overflow-hidden rounded-lg border ${production ? "border-red-500/60 bg-red-500/[0.03]" : "border-emerald-500/50 bg-emerald-500/[0.04]"}`}
    >
      <div className={`px-4 py-2 font-mono text-[11px] font-black tracking-[0.16em] ${production ? "bg-red-600 text-white" : "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"}`}>
        {production ? "PRODUCTION — READ ONLY" : "STAGING"}
      </div>
      <dl className="grid gap-4 p-4 sm:grid-cols-3">
        <InventoryValue label="Domain" value={environment.domain} />
        <InventoryValue label="Branch" value={environment.branch} />
        <InventoryValue label="Runtime path" value={environment.runtime_path} />
      </dl>
    </section>
  );
}

export default function ApplicationsTab({ token }: ApplicationsTabProps) {
  const [applications, setApplications] = useState<ApplicationInventoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    fetchApplications(token)
      .then((items) => active && setApplications(items))
      .catch(() => active && setFailed(true))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [token]);

  return (
    <div className="flex flex-col gap-6">
      <header className="border-b border-border-sem pb-5">
        <p className="font-mono text-[10px] font-bold uppercase tracking-[0.24em] text-cobalt">Phase 1 / Inventory</p>
        <h2 className="mt-2 text-3xl font-black tracking-tight">Applications</h2>
        <p className="mt-2 max-w-2xl text-sm text-muted-sem">A read-only map of application source and runtime environments.</p>
      </header>

      {loading && <p role="status" className="font-mono text-sm text-muted-sem">Loading application inventory...</p>}
      {failed && <p role="alert" className="rounded-lg border border-red-500/40 bg-red-500/5 p-4 text-sm">Application inventory is unavailable. Try again later.</p>}
      {!loading && !failed && applications.length === 0 && (
        <p className="rounded-lg border border-border-sem p-5 text-sm text-muted-sem">No applications are recorded.</p>
      )}

      <div className="grid gap-5 xl:grid-cols-2">
        {applications.map((application) => (
          <article key={application.id} className="flat-card flex flex-col gap-5 p-5 md:p-6">
            <header>
              <h3 className="text-xl font-black tracking-tight">{application.display_name}</h3>
              <p className="mt-3 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-sem">Source</p>
              <p className={`mt-1 break-all font-mono text-xs ${application.source_path ? "text-foreground-sem" : "text-muted-sem italic"}`}>
                {application.source_path || "Source not recorded"}
              </p>
            </header>
            <div className="flex flex-col gap-3">
              {application.environments.length > 0 ? application.environments.map((environment) => (
                <EnvironmentCard key={environment.id} environment={environment} />
              )) : (
                <p className="rounded-lg border border-dashed border-border-sem p-4 text-sm text-muted-sem">No environments recorded</p>
              )}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
