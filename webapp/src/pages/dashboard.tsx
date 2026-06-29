import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { RefreshCw, ExternalLink } from "lucide-react";
import API_BASE from "@/lib/api";
import { useLogger } from "../context/logger-context";

interface GradeEntry {
  grade: string | null;
  score: number | null;
  fetched_at: number;
}

interface RepoRow {
  repo: string;
  platforms: Record<string, GradeEntry>;
}

const PLATFORM_NAMES: Record<string, string> = {
  toolbench: "ToolBench",
  glama: "Glama",
  lobehub: "LobeHub",
};

const GRADE_COLORS: Record<string, string> = {
  "A+": "bg-emerald-600",
  A: "bg-emerald-500",
  B: "bg-blue-500",
  C: "bg-yellow-500",
  D: "bg-orange-500",
  F: "bg-red-500",
  "N/A": "bg-slate-600",
  "?": "bg-slate-600",
};

function GradeBadge({ grade }: { grade: string | null }) {
  const g = grade || "?";
  return (
    <span className={`inline-flex items-center justify-center w-8 h-6 rounded text-xs font-bold text-white ${GRADE_COLORS[g] || "bg-slate-600"}`}>
      {g}
    </span>
  );
}

export default function Dashboard() {
  const { append } = useLogger();
  const [data, setData] = useState<{
    repos: Record<string, Record<string, GradeEntry>>;
    platforms: string[];
    repo_count: number;
    fleet_total?: number;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMsg, setRefreshMsg] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(API_BASE + "/api/coverage");
      const json = await r.json();
      setData(json);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleRefresh = async () => {
    setRefreshing(true);
    setRefreshMsg(null);
    append("INFO", "Fleet grade refresh started");
    try {
      const r = await fetch(API_BASE + "/api/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const json = await r.json();
      if (!r.ok) throw new Error(json.detail || `HTTP ${r.status}`);
      const msg =
        (json.message as string) ||
        `Updated ${json.refreshed ?? 0} remote grade(s) in ${json.duration_ms ?? "?"}ms`;
      setRefreshMsg(msg);
      append("INFO", msg);
      await fetchData();
    } catch (e) {
      const err = e instanceof Error ? e.message : "refresh failed";
      setRefreshMsg(err);
      append("ERROR", err);
    }
    setRefreshing(false);
  };

  const rows: RepoRow[] = data
    ? Object.entries(data.repos)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([repo, platforms]) => ({ repo, platforms }))
    : [];

  const allPlatforms = data?.platforms || ["toolbench", "glama", "lobehub"];

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Fleet Coverage Matrix</h2>
          <p className="text-sm text-slate-400 mt-1">
            {data
              ? `${data.repo_count} repos in matrix${data.fleet_total ? ` (${data.fleet_total} fleet)` : ""}`
              : "Loading..."}{" "}
            across {allPlatforms.length} platforms
          </p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="flex items-center gap-2 px-4 py-2 bg-fleet-600 hover:bg-fleet-500 disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
        >
          <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
          {refreshing ? "Scanning..." : "Refresh All"}
        </button>
      </div>

      {refreshMsg && (
        <div className="mb-4 text-sm text-slate-300 glass-panel px-4 py-3">{refreshMsg}</div>
      )}

      {loading && !data ? (
        <div className="text-slate-500 text-sm">Loading coverage data...</div>
      ) : rows.length === 0 ? (
        <div className="text-slate-500 text-sm">
          No fleet repos in registry. Set SCRAPER_FLEET_REGISTRY or install mcp-central-docs registry.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800">
                <th className="text-left py-2 px-3 text-slate-400 font-medium">Repo</th>
                {allPlatforms.map((p) => (
                  <th key={p} className="text-center py-2 px-3 text-slate-400 font-medium">
                    {PLATFORM_NAMES[p] || p}
                  </th>
                ))}
                <th className="text-center py-2 px-3 text-slate-400 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.repo} className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
                  <td className="py-2 px-3">
                    <Link to={`/repo/${row.repo}`} className="text-fleet-400 hover:text-fleet-300 font-mono text-xs">
                      {row.repo}
                    </Link>
                  </td>
                  {allPlatforms.map((p) => (
                    <td key={p} className="py-2 px-3 text-center">
                      {row.platforms[p] ? (
                        <GradeBadge grade={row.platforms[p].grade} />
                      ) : (
                        <span className="text-slate-700 text-xs">—</span>
                      )}
                    </td>
                  ))}
                  <td className="py-2 px-3 text-center">
                    <a
                      href={`https://github.com/sandraschi/${row.repo}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-slate-500 hover:text-slate-300"
                    >
                      <ExternalLink size={12} />
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
