import { useState, useEffect, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, RefreshCw, ExternalLink, History, BarChart3, AlertTriangle, CheckCircle } from "lucide-react";
import API_BASE from "@/lib/api";

interface ToolDetail {
  name: string;
  grade?: string;
  score?: number;
  tool_score?: number;
  purpose?: number;
  usage_guidelines?: number;
  behavior?: number;
  parameters?: number;
  conciseness?: number;
  completeness?: number;
}

interface RawData {
  url?: string;
  tools?: number;
  tool_details?: ToolDetail[];
  tdqs_mean?: number;
  tdqs_min?: number;
  tdqs_grade?: string;
  coherence_grade?: string;
  maintenance_grade?: string;
  latest_release?: string;
  definition_score?: number;
  protocol_score?: number;
  supportability_score?: number;
  trust_score?: number;
  top_issues?: string[];
  server_id?: string;
}

interface GradeInfo {
  grade: string | null;
  score: number | null;
  url?: string;
  tools?: number;
  raw?: RawData;
  fetched_at: number;
}

interface HistoryEntry {
  grade: string | null;
  score: number | null;
  recorded_at: number;
  raw?: RawData;
}

const PLATFORM_NAMES: Record<string, string> = {
  toolbench: "ToolBench",
  glama: "Glama",
  lobehub: "LobeHub",
};

const GRADE_COLORS: Record<string, string> = {
  "A+": "bg-emerald-600", A: "bg-emerald-500", B: "bg-blue-500",
  C: "bg-yellow-500", D: "bg-orange-500", F: "bg-red-500",
};

function GradeTag({ grade, score }: { grade: string | null; score?: number | null }) {
  const g = grade || "?";
  return (
    <span className={`text-xs px-2 py-0.5 rounded font-medium text-white ${GRADE_COLORS[g] || "bg-slate-700"}`}>
      {g}{score != null ? ` (${typeof score === "number" ? score.toFixed(1) : score})` : ""}
    </span>
  );
}

function DimBar({ label, value, max = 5 }: { label: string; value?: number; max?: number }) {
  if (value == null) return null;
  const pct = (value / max) * 100;
  const color = value >= 4 ? "bg-emerald-500" : value >= 3 ? "bg-blue-500" : value >= 2 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-20 text-slate-500 shrink-0">{label}</span>
      <div className="flex-1 bg-slate-800 rounded-full h-2 overflow-hidden">
        <div className={`h-full rounded-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-8 text-right text-slate-400 font-mono">{value.toFixed(1)}</span>
    </div>
  );
}

function HistorySparkline({ entries }: { entries: HistoryEntry[] }) {
  if (entries.length < 2) return null;
  return (
    <div className="flex items-center gap-1">
      {entries.slice(0, 10).reverse().map((h, i) => {
        const g = h.grade || "?";
        const c = GRADE_COLORS[g] || "bg-slate-700";
        return (
          <span key={i} title={`${new Date((h.recorded_at || 0) * 1000).toLocaleDateString()}: ${g}`}
                className={`block w-3 h-4 rounded-sm ${c} opacity-${Math.max(20, 100 - i * 8)}`} />
        );
      })}
    </div>
  );
}

export default function RepoDetail() {
  const { repoName } = useParams<{ repoName: string }>();
  const [grades, setGrades] = useState<Record<string, GradeInfo>>({});
  const [history, setHistory] = useState<Record<string, HistoryEntry[]>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = useCallback(async () => {
    if (!repoName) return;
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/api/coverage/${repoName}`);
      const json = await r.json();
      const gradeMap: Record<string, GradeInfo> = {};
      for (const g of json.grades || []) {
        gradeMap[g.platform] = {
          grade: g.grade, score: g.score,
          url: g.raw?.url || g.url,
          tools: g.raw?.tools || g.tools,
          raw: g.raw, fetched_at: g.fetched_at,
        };
      }
      setGrades(gradeMap);
      setHistory(json.history || {});
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [repoName]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleRefresh = async () => {
    if (!repoName) return;
    setRefreshing(true);
    try {
      await fetch(API_BASE + "/api/refresh", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo: repoName }),
      });
      await fetchData();
    } catch (e) { console.error(e); }
    setRefreshing(false);
  };

  // Compute Glama TDQS deltas
  const glamaRaw = grades.glama?.raw;
  const glamaHistory = history.glama || [];
  const prevGlamaRaw = glamaHistory.length > 1 ? glamaHistory[1]?.raw : null;

  function tdqsDelta(current?: number, prev?: number): string | null {
    if (current == null || prev == null || prev === 0) return null;
    const d = current - prev;
    if (Math.abs(d) < 0.01) return null;
    return d > 0 ? `+${d.toFixed(2)}` : d.toFixed(2);
  }

  return (
    <div data-testid="repo-detail">
      <div className="flex items-center gap-4 mb-6">
        <Link to="/" className="text-slate-500 hover:text-slate-300"><ArrowLeft size={18} /></Link>
        <h2 className="text-lg font-semibold text-slate-100 font-mono">{repoName}</h2>
        <a href={`https://github.com/sandraschi/${repoName}`} target="_blank" rel="noopener noreferrer"
           className="text-slate-500 hover:text-slate-300"><ExternalLink size={14} /></a>
        <button onClick={handleRefresh} disabled={refreshing}
                className="ml-auto flex items-center gap-2 px-3 py-1.5 bg-fleet-600 hover:bg-fleet-500 disabled:opacity-50 rounded text-xs font-medium transition-colors">
          <RefreshCw size={12} className={refreshing ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {loading ? (
        <div className="text-slate-500 text-sm">Loading...</div>
      ) : Object.keys(grades).length === 0 ? (
        <div className="text-slate-500 text-sm">No grade data. Click Refresh to scan.</div>
      ) : (
        <div className="space-y-4">
          {Object.entries(grades).map(([pid, info]) => {
            const raw = info.raw;
            const hist = history[pid] || [];
            const prevRaw = hist.length > 1 ? hist[1]?.raw : null;
            return (
              <div key={pid} data-testid={`grade-${pid}`} className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                {/* Header */}
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold text-slate-200">{PLATFORM_NAMES[pid] || pid}</h3>
                  <div className="flex items-center gap-2">
                    <GradeTag grade={info.grade} score={info.score} />
                    {pid === "toolbench" && info.url && (
                      <button
                        data-testid="toolbench-fix-btn"
                        onClick={async () => {
                          const btn = document.activeElement as HTMLButtonElement;
                          btn.disabled = true;
                          btn.textContent = "...";
                          try {
                            const r = await fetch(API_BASE + "/api/scraper/fix/" + encodeURIComponent(repoName || ""), { method: "POST" });
                            const j = await r.json();
                            alert("Fix scan: " + j.message);
                          } catch {
                            alert("Fix scan failed");
                          }
                          btn.disabled = false;
                          btn.textContent = "Fix w/ AI";
                        }}
                        className="text-[10px] px-2 py-1 rounded bg-amber-600/20 text-amber-400 hover:bg-amber-600/30 border border-amber-700/30 transition-colors disabled:opacity-50"
                        title="Auto-fix based on ToolBench criticism"
                      >
                        Fix w/ AI
                      </button>
                    )}
                  </div>
                </div>

                {/* Metadata */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-slate-500 mb-3">
                  {info.tools != null && <div>Tools: <span className="text-slate-300">{info.tools}</span></div>}
                  {raw?.tdqs_mean && <div>TDQS &mu;: <span className="text-slate-300">{raw.tdqs_mean}</span></div>}
                  {raw?.tdqs_min && <div>TDQS min: <span className="text-slate-300">{raw.tdqs_min}</span></div>}
                  {raw?.coherence_grade && <div>Coherence: <span className="text-slate-300">{raw.coherence_grade}</span></div>}
                  {raw?.maintenance_grade && <div>Maintenance: <span className="text-slate-300">{raw.maintenance_grade}</span></div>}
                  {raw?.latest_release && <div>Release: <span className="text-slate-300">{raw.latest_release}</span></div>}
                  {raw?.definition_score != null && <div>Definition: <span className="text-slate-300">{raw.definition_score}%</span></div>}
                  {raw?.protocol_score != null && <div>Protocol: <span className="text-slate-300">{raw.protocol_score}%</span></div>}
                  {raw?.supportability_score != null && <div>Supportability: <span className="text-slate-300">{raw.supportability_score}%</span></div>}
                  {raw?.trust_score != null && <div>Trust: <span className="text-slate-300">{raw.trust_score}</span></div>}
                </div>

                {/* TDQS dimension bars (Glama) */}
                {raw?.tool_details && raw.tool_details.length > 0 && (
                  <div className="mb-3">
                    <h4 className="text-xs text-slate-500 font-medium mb-1.5 flex items-center gap-1">
                      <BarChart3 size={11} /> Per-Tool TDQS Dimensions
                    </h4>
                    <div className="space-y-1 max-h-48 overflow-y-auto">
                      {raw.tool_details.slice(0, 15).map((t) => {
                        if (!t.purpose && !t.behavior) return null;
                        return (
                          <div key={t.name} className="bg-slate-800/50 rounded px-2 py-1.5">
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-xs text-slate-300 font-mono">{t.name}</span>
                              <span className={`text-[10px] px-1 rounded ${t.grade ? GRADE_COLORS[t.grade] || "bg-slate-600" : "bg-slate-600"} text-white`}>
                                {t.grade || "?"} {t.score != null ? t.score.toFixed(1) : ""}
                              </span>
                            </div>
                            <div className="grid grid-cols-3 gap-x-3 gap-y-0.5">
                              <DimBar label="Purpose" value={t.purpose} />
                              <DimBar label="Usage" value={t.usage_guidelines} />
                              <DimBar label="Behavior" value={t.behavior} />
                              <DimBar label="Params" value={t.parameters} />
                              <DimBar label="Conciseness" value={t.conciseness} />
                              <DimBar label="Complete" value={t.completeness} />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* ToolBench: per-tool scores */}
                {raw?.tool_details && pid === "toolbench" && raw.tool_details.some((t) => t.tool_score) && (
                  <div className="mb-3">
                    <h4 className="text-xs text-slate-500 font-medium mb-1.5 flex items-center gap-1">
                      <AlertTriangle size={11} /> Per-Tool Scores (lower = needs attention)
                    </h4>
                    <div className="flex flex-wrap gap-1.5">
                      {(raw.tool_details || []).sort((a, b) => (a.tool_score || 0) - (b.tool_score || 0)).slice(0, 10).map((t) => (
                        <span key={t.name} title={t.name} className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                          (t.tool_score || 0) < 50 ? "bg-red-900/50 text-red-300" :
                          (t.tool_score || 0) < 70 ? "bg-amber-900/50 text-amber-300" :
                          "bg-slate-700 text-slate-400"
                        }`}>
                          {t.name}:{t.tool_score}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Top Issues (ToolBench) */}
                {raw?.top_issues && raw.top_issues.length > 0 && (
                  <div className="mb-3">
                    <h4 className="text-xs text-slate-500 font-medium mb-1.5">Top Issues</h4>
                    <ul className="space-y-1">
                      {raw.top_issues.slice(0, 4).map((issue, i) => (
                        <li key={i} className="text-xs text-slate-400 flex items-start gap-1.5">
                          <span className="text-red-400 mt-0.5 shrink-0">&bull;</span>
                          {issue.length > 120 ? issue.slice(0, 120) + "..." : issue}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* History */}
                {hist.length > 1 && (
                  <div className="pt-3 border-t border-slate-800">
                    <div className="flex items-center gap-2 text-xs text-slate-500 mb-1.5">
                      <History size={10} /> Grade History
                      <HistorySparkline entries={hist} />
                    </div>
                    <div className="flex gap-1 flex-wrap">
                      {hist.slice(0, 8).map((h, i) => (
                        <span key={i} className={`text-[10px] px-1 py-0.5 rounded ${GRADE_COLORS[h.grade || "?"] || "bg-slate-700"} text-white`}
                              title={new Date((h.recorded_at || 0) * 1000).toLocaleString()}>
                          {h.grade || "?"}{h.score != null ? ` ${typeof h.score === "number" ? h.score.toFixed(0) : h.score}` : ""}
                        </span>
                      ))}
                    </div>

                    {/* TDQS mean delta */}
                    {raw?.tdqs_mean != null && prevRaw?.tdqs_mean != null && (() => {
                      const d = raw.tdqs_mean! - prevRaw.tdqs_mean!;
                      if (Math.abs(d) < 0.01) return null;
                      return (
                        <div className="text-xs text-slate-500 mt-1">
                          TDQS &mu; changed: {prevRaw.tdqs_mean?.toFixed(2)} &rarr; {raw.tdqs_mean?.toFixed(2)}
                          <span className={d > 0 ? "text-emerald-400" : "text-red-400"}>
                            {" "}({d > 0 ? "+" : ""}{d.toFixed(2)})
                          </span>
                        </div>
                      );
                    })()}
                  </div>
                )}

                {/* Link */}
                {info.url && (
                  <div className="mt-2 pt-2 border-t border-slate-800/50">
                    <a href={info.url} target="_blank" rel="noopener noreferrer"
                       className="text-xs text-fleet-400 hover:text-fleet-300 flex items-center gap-1">
                      View full report <ExternalLink size={10} />
                    </a>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
