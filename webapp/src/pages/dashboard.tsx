import { useState, useEffect, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { RefreshCw, ExternalLink, Search } from "lucide-react";
import API_BASE from "@/lib/api";
import { useLogger } from "../context/logger-context";

interface GradeEntry {
  grade: string | null;
  score: number | null;
  url: string;
  fetched_at: number;
}

interface RepoRow {
  repo: string;
  platforms: Record<string, GradeEntry>;
}

interface CoverageData {
  repos: Record<string, Record<string, GradeEntry>>;
  platforms: string[];
  repo_count: number;
  fleet_total?: number;
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

type SortKey = "repo" | "toolbench" | "glama" | "lobehub" | "stale";

function daysSince(ts: number): number {
  return Math.floor((Date.now() / 1000 - ts) / 86400);
}

function stalenessColor(days: number): string {
  if (days <= 1) return "text-emerald-500";
  if (days <= 3) return "text-blue-400";
  if (days <= 7) return "text-amber-400";
  return "text-red-400";
}

function GradeBadge({ grade, url }: { grade: string | null; url?: string }) {
  const g = grade || "?";
  const cls = `inline-flex items-center justify-center w-8 h-6 rounded text-xs font-bold text-white ${GRADE_COLORS[g] || "bg-slate-600"}`;
  if (url) {
    return (
      <a href={url} target="_blank" rel="noopener noreferrer" title={`View on ${url}`} className={cls}>
        {g}
      </a>
    );
  }
  return <span className={cls}>{g}</span>;
}

function sortGrade(g: string | null): number {
  const order: Record<string, number> = { "A+": 0, A: 1, B: 2, C: 3, D: 4, F: 5, "?": 6, "N/A": 7 };
  return order[g || "?"] ?? 99;
}

export default function Dashboard() {
  const { append } = useLogger();
  const [data, setData] = useState<CoverageData | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMsg, setRefreshMsg] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("repo");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [filter, setFilter] = useState("");

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(API_BASE + "/api/coverage");
      setData(await r.json());
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
      const msg = json.message || `Updated ${json.refreshed ?? 0} grades`;
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

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const sortArrow = (key: SortKey) =>
    sortKey === key ? (sortDir === "asc" ? " \u25B2" : " \u25BC") : "";

  const rows: RepoRow[] = useMemo(() => {
    if (!data) return [];
    let list = Object.entries(data.repos)
      .map(([repo, platforms]) => ({ repo, platforms }));

    // Filter
    if (filter) {
      const f = filter.toLowerCase();
      list = list.filter(
        (r) =>
          r.repo.toLowerCase().includes(f) ||
          Object.entries(r.platforms).some(
            ([, g]) => g.grade && g.grade.toLowerCase().includes(f)
          )
      );
    }

    // Sort
    const allPlatforms = data?.platforms || ["toolbench", "glama", "lobehub"];
    list.sort((a, b) => {
      let cmp = 0;
      if (sortKey === "repo") {
        cmp = a.repo.localeCompare(b.repo);
      } else if (sortKey === "stale") {
        const p = allPlatforms.find((pl) => a.platforms[pl]);
        const aDays = p ? daysSince(a.platforms[p]?.fetched_at ?? 0) : 999;
        const bDays = p ? daysSince(b.platforms[p]?.fetched_at ?? 0) : 999;
        cmp = aDays - bDays;
      } else {
        const aGrade = sortGrade(a.platforms[sortKey]?.grade ?? null);
        const bGrade = sortGrade(b.platforms[sortKey]?.grade ?? null);
        cmp = aGrade - bGrade;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    return list;
  }, [data, sortKey, sortDir, filter]);

  const allPlatforms = data?.platforms || ["toolbench", "glama", "lobehub"];

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Fleet Coverage Matrix</h2>
          <p className="text-sm text-slate-400 mt-1">
            {data
              ? `${data.repo_count} repos${data.fleet_total ? ` (${data.fleet_total} fleet)` : ""}`
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

      {/* Filter bar */}
      <div className="relative mb-4">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-600" />
        <input
          type="text"
          placeholder="Filter repos or grades..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="w-full bg-slate-900 border border-slate-700 rounded-lg pl-9 pr-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-fleet-500"
        />
      </div>

      {loading && !data ? (
        <div className="text-slate-500 text-sm">Loading coverage data...</div>
      ) : rows.length === 0 ? (
        <div className="text-slate-500 text-sm">
          {filter ? "No repos match filter." : "No fleet repos in registry."}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800">
                <th
                  className="text-left py-2 px-3 text-slate-400 font-medium cursor-pointer hover:text-slate-200 select-none"
                  onClick={() => toggleSort("repo")}
                >
                  Repo{sortArrow("repo")}
                </th>
                {allPlatforms.map((p) => (
                  <th
                    key={p}
                    className="text-center py-2 px-3 text-slate-400 font-medium cursor-pointer hover:text-slate-200 select-none"
                    onClick={() => toggleSort(p as SortKey)}
                  >
                    {PLATFORM_NAMES[p] || p}{sortArrow(p as SortKey)}
                  </th>
                ))}
                <th
                  className="text-center py-2 px-3 text-slate-400 font-medium cursor-pointer hover:text-slate-200 select-none"
                  onClick={() => toggleSort("stale")}
                >
                  Data{sortArrow("stale")}
                </th>
                <th className="text-center py-2 px-3 text-slate-400 font-medium">Links</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const first = allPlatforms.find((p) => row.platforms[p]);
                const days = first ? daysSince(row.platforms[first]?.fetched_at ?? 0) : -1;
                return (
                  <tr key={row.repo} className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
                    <td className="py-2 px-3">
                      <Link to={`/repo/${row.repo}`} className="text-fleet-400 hover:text-fleet-300 font-mono text-xs">
                        {row.repo}
                      </Link>
                    </td>
                    {allPlatforms.map((p) => (
                      <td key={p} className="py-2 px-3 text-center">
                        {row.platforms[p] ? (
                          <GradeBadge grade={row.platforms[p].grade} url={row.platforms[p].url} />
                        ) : (
                          <span className="text-slate-700 text-xs">&mdash;</span>
                        )}
                      </td>
                    ))}
                    <td className="py-2 px-3 text-center text-xs">
                      {days >= 0 ? (
                        <span className={stalenessColor(days)}>
                          {days === 0 ? "today" : `${days}d`}
                        </span>
                      ) : (
                        <span className="text-slate-700">&mdash;</span>
                      )}
                    </td>
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
                );
              })}
            </tbody>
          </table>
          <p className="text-xs text-slate-600 mt-2">
            {rows.length} repo{rows.length !== 1 ? "s" : ""}
            {filter ? ` (filtered)` : ""}
            {" \u00B7 "}Click column headers to sort
            {" \u00B7 "}Grade badges link to platform reviews
          </p>
        </div>
      )}
    </div>
  );
}
