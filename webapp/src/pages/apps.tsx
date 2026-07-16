import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import API_BASE from "@/lib/api";

type FleetApp = {
  id: string;
  name: string;
  description: string;
  port: number;
  category: string;
  url: string | null;
};

export default function AppsPage() {
  const [apps, setApps] = useState<FleetApp[]>([]);
  const [fleetTotal, setFleetTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(API_BASE + "/api/apps")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((j) => {
        setApps((j.apps as FleetApp[]) ?? []);
        setFleetTotal(j.fleet_total ?? 0);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "load failed"));
  }, []);

  const withPort = apps.filter((a) => a.port > 0);

  return (
    <div data-testid="apps">
      <h2 className="text-lg font-semibold text-slate-100 mb-2">Fleet Apps Hub</h2>
      <p className="text-sm text-slate-400 mb-4">
        {fleetTotal} repos in fleet registry · {withPort.length} with assigned webapp ports
      </p>
      {error && <p className="text-sm text-red-400 mb-4">{error}</p>}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {withPort.slice(0, 60).map((app) => (
          <div key={app.id} className="glass-panel p-4">
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="font-mono text-sm text-fleet-400">{app.id}</div>
                <div className="text-xs text-slate-500 mt-1">:{app.port} · {app.category || "—"}</div>
              </div>
              {app.url && (
                <a href={app.url} target="_blank" rel="noopener noreferrer" className="text-slate-500 hover:text-slate-300">
                  <ExternalLink size={14} />
                </a>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-2 line-clamp-3">{app.description}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
