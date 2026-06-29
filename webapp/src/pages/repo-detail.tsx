import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, RefreshCw, ExternalLink, History } from "lucide-react";
import API_BASE from "@/lib/api";

interface GradeInfo {
  grade: string | null;
  score: number | null;
  url?: string;
  tools?: number;
  fetched_at: number;
}

interface HistoryEntry {
  grade: string | null;
  score: number | null;
  recorded_at: number;
}

const PLATFORM_NAMES: Record<string, string> = {
  toolbench: "ToolBench",
  glama: "Glama",
  lobehub: "LobeHub",
};

export default function RepoDetail() {
  const { repoName } = useParams<{ repoName: string }>();
  const [grades, setGrades] = useState<Record<string, GradeInfo>>({});
  const [history, setHistory] = useState<Record<string, HistoryEntry[]>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = async () => {
    if (!repoName) return;
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/api/coverage/${repoName}`);
      const json = await r.json();
      const gradeMap: Record<string, GradeInfo> = {};
      for (const g of json.grades || []) {
        gradeMap[g.platform] = {
          grade: g.grade,
          score: g.score,
          url: g.url || (g.raw || {}).url,
          tools: g.tools || (g.raw || {}).tools,
          fetched_at: g.fetched_at,
        };
      }
      setGrades(gradeMap);
      setHistory(json.history || {});
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  useEffect(() => { fetchData(); }, [repoName]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await fetch(API_BASE + "/api/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo: repoName }),
      });
      await fetchData();
    } catch (e) {
      console.error(e);
    }
    setRefreshing(false);
  };

  return (
    <div>
      <div className="flex items-center gap-4 mb-6">
        <Link to="/" className="text-slate-500 hover:text-slate-300">
          <ArrowLeft size={18} />
        </Link>
        <h2 className="text-lg font-semibold text-slate-100 font-mono">{repoName}</h2>
        <a
          href={`https://github.com/sandraschi/${repoName}`}
          target="_blank"
          rel="noopener noreferrer"
          className="text-slate-500 hover:text-slate-300"
        >
          <ExternalLink size={14} />
        </a>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="ml-auto flex items-center gap-2 px-3 py-1.5 bg-fleet-600 hover:bg-fleet-500 disabled:opacity-50 rounded text-xs font-medium transition-colors"
        >
          <RefreshCw size={12} className={refreshing ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {loading ? (
        <div className="text-slate-500 text-sm">Loading...</div>
      ) : Object.keys(grades).length === 0 ? (
        <div className="text-slate-500 text-sm">No grade data. Click Refresh to scan.</div>
      ) : (
        <div className="space-y-4">
          {Object.entries(grades).map(([pid, info]) => (
            <div key={pid} className="bg-slate-900 border border-slate-800 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-semibold text-slate-200">{PLATFORM_NAMES[pid] || pid}</h3>
                <span className={`text-xs px-2 py-0.5 rounded ${info.grade === "F" ? "bg-red-500/20 text-red-400" : info.grade === "A" || info.grade === "A+" ? "bg-emerald-500/20 text-emerald-400" : "bg-slate-700 text-slate-300"}`}>
                  {info.grade || "?"} {info.score != null ? `(${info.score})` : ""}
                </span>
              </div>
              <div className="text-xs text-slate-500 space-y-1">
                {info.tools != null && <div>Tools indexed: {info.tools}</div>}
                {info.url && (
                  <a href={info.url} target="_blank" rel="noopener noreferrer" className="text-fleet-400 hover:text-fleet-300 block">
                    View on {PLATFORM_NAMES[pid]} →
                  </a>
                )}
                {info.fetched_at && (
                  <div>Last checked: {new Date(info.fetched_at * 1000).toLocaleString()}</div>
                )}
              </div>

              {history[pid] && history[pid].length > 1 && (
                <div className="mt-3 pt-3 border-t border-slate-800">
                  <div className="flex items-center gap-1 text-xs text-slate-500 mb-1">
                    <History size={10} /> Grade History
                  </div>
                  <div className="flex gap-1.5 flex-wrap">
                    {history[pid].slice(0, 10).map((h, i) => (
                      <span key={i} className={`text-[10px] px-1.5 py-0.5 rounded ${h.grade === "F" ? "bg-red-600/30" : h.grade === "A" || h.grade === "A+" ? "bg-emerald-600/30" : "bg-slate-700"} text-slate-300`}>
                        {h.grade || "?"}{h.score != null ? ` ${h.score}` : ""}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
