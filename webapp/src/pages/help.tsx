import { useState } from "react";
import {
  BookOpen, Radio, Wrench, Terminal, FileText, ExternalLink,
  CheckCircle, AlertTriangle, BarChart3, Code, Layers, RefreshCw
} from "lucide-react";

type Tab = "overview" | "platforms" | "tools" | "api" | "standards";

const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
  { id: "overview", label: "Overview", icon: BookOpen },
  { id: "platforms", label: "Platforms", icon: Radio },
  { id: "tools", label: "MCP Tools", icon: Wrench },
  { id: "api", label: "API", icon: Terminal },
  { id: "standards", label: "Standards", icon: FileText },
];

const TOOLS = [
  {
    name: "scraper_refresh",
    desc: "Scan all platforms for fleet repo grades. Use before viewing coverage to ensure fresh data.",
    ops: "No operation param — call directly. Optional: repo= for single-repo scan.",
  },
  {
    name: "scraper_matrix",
    desc: "Coverage matrix showing which fleet repos are indexed on each platform with grades.",
    ops: "Read-only. Returns repos × platforms grid with grade letters and scores.",
  },
  {
    name: "scraper_repo",
    desc: "Detailed grade report for one repo across all platforms, with history deltas.",
    ops: "Requires repo param. Shows current grades, platform URLs, and change history.",
  },
  {
    name: "scraper_reassess",
    desc: "Request rescoring on grading platforms after shipping fixes.",
    ops: "Requires repo param. Optional: platform= to target one platform.",
  },
  {
    name: "scraper_platforms",
    desc: "List registered grading platforms and their status.",
    ops: "Operation: list (default), info <platform>, add <name> <url>.",
  },
  {
    name: "scraper_improvement_plan",
    desc: "Prioritized fix list from ToolBench criticisms, mapped to fleet standards.",
    ops: "Requires repo. Filters portmanteau exceptions. Sorted by severity.",
  },
  {
    name: "scraper_improve_suggest",
    desc: "Concrete copy-paste code snippets for each ToolBench issue pattern.",
    ops: "Requires repo. Generates Python code for Literal constraints, docstrings, error handling, etc.",
  },
  {
    name: "toolbench_guide",
    desc: "Curated ToolBench context: methodology, rescoring steps, Glama comparison.",
    ops: "Operations: get_help, list_official_links, rescoring_after_improvements, glama_vs_toolbench, arcade_mcp_product.",
  },
];

const PLATFORMS = [
  {
    id: "toolbench",
    name: "ToolBench",
    url: "https://toolbench.arcade.dev",
    desc: "Arcade.dev's MCP server quality benchmark. Grades on Definition Quality (50%), Protocol Readiness (20%), and Supportability (30%). Assigns A+/A/B/C/D/F grades with per-tool risk scores and top-issue narratives.",
    color: "text-amber-400",
    strengths: ["Per-tool risk scores", "Concrete issue descriptions", "Pattern-linked improvement hints", "Public methodology"],
    limits: ["Anti-portmanteau bias (fleet exception)", "Stdio-only servers capped at 50 on protocol", "Supportability favors popular repos"],
  },
  {
    id: "glama",
    name: "Glama.ai",
    url: "https://glama.ai",
    desc: "MCP server registry with per-tool TDQS (Tool Definition Quality Score) grading. Scores each tool on 6 dimensions (Purpose, Usage, Behavior, Parameters, Conciseness, Completeness). Server grade = 60% mean + 40% minimum across tools.",
    color: "text-emerald-400",
    strengths: ["Per-tool dimension breakdowns", "60/40 mean/min formula highlights worst tool", "Daily auto-rescan", "No stars/repo-size bias"],
    limits: ["Only evaluates docstrings, not runtime", "Requires manual 'Sync Server' for immediate refresh", "No per-issue improvement hints"],
  },
  {
    id: "lobehub",
    name: "LobeHub",
    url: "https://lobehub.com",
    desc: "Open-source MCP marketplace. Lists servers with metadata but no public grading API. Presence indicates the server is indexed and discoverable.",
    color: "text-blue-400",
    strengths: ["Wide discoverability", "Open-source catalog"],
    limits: ["No grades or quality signals", "No rescoring API"],
  },
];

const API_ENDPOINTS = [
  { method: "GET", path: "/health", desc: "Health check with uptime and port info" },
  { method: "GET", path: "/api/capabilities", desc: "Capability introspection (tools, prompts, resources)" },
  { method: "GET", path: "/api/coverage", desc: "Coverage matrix: repos × platforms with grades + URLs" },
  { method: "GET", path: "/api/coverage/{repo}", desc: "Single-repo grade detail from all platforms" },
  { method: "GET", path: "/api/tools", desc: "Flat MCP tool list with descriptions" },
  { method: "GET", path: "/api/status", desc: "Server status, uptime, repo/platform counts" },
  { method: "POST", path: "/api/refresh", desc: "Trigger grade refresh (all or single repo)" },
  { method: "GET", path: "/api/apps", desc: "Fleet registry slice for /apps page" },
  { method: "GET", path: "/api/llm/providers", desc: "Probe local Ollama/LM Studio models" },
  { method: "POST", path: "/api/llm/chat", desc: "Chat via local Ollama model" },
  { method: "GET", path: "/api/scraper/status", desc: "ToolBench Playwright archiver status" },
  { method: "GET", path: "/api/logs", desc: "Activity log query with filters" },
  { method: "GET", path: "/mcp", desc: "FastMCP Streamable HTTP transport" },
];

const FLEET_DOCS = [
  { name: "TOOL_DESIGN_STANDARDS.md", url: "https://github.com/sandraschi/mcp-central-docs/blob/main/standards/TOOL_DESIGN_STANDARDS.md", desc: "Docstring template, param constraints, return values, pagination, annotations, error handling" },
  { name: "GLAMA_SCORING.md", url: "https://github.com/sandraschi/mcp-central-docs/blob/main/toolbench/GLAMA_SCORING.md", desc: "TDQS 6 dimensions, grade thresholds, F-to-C fix workflow" },
  { name: "ARCADE_TOOLBENCH_ASSESSMENT.md", url: "https://github.com/sandraschi/mcp-central-docs/blob/main/toolbench/ARCADE_TOOLBENCH_ASSESSMENT.md", desc: "ToolBench methodology deep-dive, biases, stdio cap, stars weighting" },
  { name: "FLEET_ALIGNMENT.md", url: "https://github.com/sandraschi/mcp-central-docs/blob/main/toolbench/FLEET_ALIGNMENT.md", desc: "Priority order for fixes, portmanteau vs benchmark conflict table" },
  { name: "JUNE_2026_STANDARDS_BAR.md", url: "https://github.com/sandraschi/mcp-central-docs/blob/main/standards/JUNE_2026_STANDARDS_BAR.md", desc: "FastMCP 3.2+, MCPB only, Prefab UI mandate, Bun adoption" },
];

function TabButton({ active, icon: Icon, label, onClick }: { active: boolean; icon: React.ElementType; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-t-lg border-b-2 transition-colors ${
        active
          ? "text-fleet-400 border-fleet-400 bg-slate-800/50"
          : "text-slate-500 border-transparent hover:text-slate-300 hover:border-slate-600"
      }`}
    >
      <Icon size={14} />
      {label}
    </button>
  );
}

export default function HelpPage() {
  const [tab, setTab] = useState<Tab>("overview");

  return (
    <div data-testid="help">
      {/* Horizontal tabs */}
      <div className="flex border-b border-slate-800 mb-6 overflow-x-auto">
        {TABS.map((t) => (
          <TabButton key={t.id} active={tab === t.id} icon={t.icon} label={t.label} onClick={() => setTab(t.id)} />
        ))}
      </div>

      {/* Tab content */}
      <div className="space-y-4 text-sm text-slate-300">
        {tab === "overview" && (
          <>
            <div className="glass-panel p-5">
              <h3 className="text-base font-semibold text-slate-100 mb-2">scraper-mcp</h3>
              <p className="text-slate-400 leading-relaxed">
                Multi-platform MCP server grade aggregator. Monitors fleet repo coverage and grades
                across <strong className="text-slate-300">ToolBench</strong> (Arcade.dev),{" "}
                <strong className="text-slate-300">Glama.ai</strong>, and{" "}
                <strong className="text-slate-300">LobeHub Marketplace</strong>.
                Provides MCP tools for querying grades, refreshing data, requesting rescoring,
                and generating prioritized improvement plans with concrete code suggestions.
              </p>
            </div>

            <div className="glass-panel p-5">
              <h3 className="text-base font-semibold text-slate-100 mb-3">Quick Start</h3>
              <ol className="space-y-2 text-slate-400">
                {[
                  ["Run", "webapp\\start.bat", "— starts backend on :10998 and frontend on :10999"],
                  ["Open", "Coverage", "— fleet repos load from the registry"],
                  ["Click", "Refresh All", "— pulls grades from ToolBench, Glama, and LobeHub"],
                  ["Click any grade badge", "— opens the platform's review page"],
                  ["Use", "Tools", "— to run MCP tools directly or use the Playwright archiver"],
                ].map(([action, target, desc], i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="text-fleet-400 font-medium shrink-0">{i + 1}.</span>
                    <span><strong className="text-slate-300">{action}</strong> <code className="text-fleet-400">{target}</code>{desc}</span>
                  </li>
                ))}
              </ol>
            </div>

            <div className="glass-panel p-5">
              <h3 className="text-base font-semibold text-slate-100 mb-3">Architecture</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                {[
                  { icon: Layers, title: "Scrapers", desc: "Three pluggable scrapers (ToolBench, Glama, LobeHub) fetch grades via HTTP APIs and HTML parsing. ToolBench assessment pages are server-rendered." },
                  { icon: BarChart3, title: "Analytics", desc: "SQLite grade store with full history for delta tracking. Each grade snapshot is preserved so you can see changes over time." },
                  { icon: Code, title: "MCP Surface", desc: "9 MCP tools expose grade data, refresh controls, improvement plans, and code suggestions to any MCP client." },
                ].map(({ icon: Icon, title, desc }) => (
                  <div key={title} className="bg-slate-800/50 rounded-lg p-3 space-y-1.5">
                    <div className="flex items-center gap-2 text-slate-100 font-medium">
                      <Icon size={14} className="text-fleet-400" />
                      {title}
                    </div>
                    <p className="text-slate-500">{desc}</p>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        {tab === "platforms" && (
          <div className="space-y-4">
            {PLATFORMS.map((p) => (
              <div key={p.id} className="glass-panel p-5">
                <div className="flex items-center justify-between mb-3">
                  <h3 className={`text-base font-semibold ${p.color}`}>{p.name}</h3>
                  <a href={p.url} target="_blank" rel="noopener noreferrer" className="text-xs text-fleet-400 hover:text-fleet-300 flex items-center gap-1">
                    Visit <ExternalLink size={10} />
                  </a>
                </div>
                <p className="text-slate-400 leading-relaxed mb-4">{p.desc}</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                  <div>
                    <h4 className="text-slate-100 font-medium mb-2 flex items-center gap-1.5">
                      <CheckCircle size={12} className="text-emerald-400" /> Strengths
                    </h4>
                    <ul className="space-y-1">
                      {p.strengths.map((s) => (
                        <li key={s} className="text-slate-500 flex items-start gap-1.5">
                          <span className="text-emerald-500 mt-0.5">+</span> {s}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <h4 className="text-slate-100 font-medium mb-2 flex items-center gap-1.5">
                      <AlertTriangle size={12} className="text-amber-400" /> Limitations
                    </h4>
                    <ul className="space-y-1">
                      {p.limits.map((l) => (
                        <li key={l} className="text-slate-500 flex items-start gap-1.5">
                          <span className="text-amber-500 mt-0.5">-</span> {l}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === "tools" && (
          <div className="space-y-3">
            {TOOLS.map((t) => (
              <div key={t.name} className="glass-panel p-4">
                <div className="flex items-center gap-2 mb-1.5">
                  <Wrench size={14} className="text-fleet-400 shrink-0" />
                  <code className="text-sm font-semibold text-slate-100">{t.name}</code>
                </div>
                <p className="text-slate-400 text-xs mb-1.5">{t.desc}</p>
                <p className="text-slate-500 text-xs">
                  <span className="text-slate-400">Usage:</span> {t.ops}
                </p>
              </div>
            ))}
          </div>
        )}

        {tab === "api" && (
          <div className="glass-panel overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800">
                  <th className="text-left py-3 px-4 text-slate-400 font-medium text-xs uppercase tracking-wider">Method</th>
                  <th className="text-left py-3 px-4 text-slate-400 font-medium text-xs uppercase tracking-wider">Path</th>
                  <th className="text-left py-3 px-4 text-slate-400 font-medium text-xs uppercase tracking-wider">Description</th>
                </tr>
              </thead>
              <tbody>
                {API_ENDPOINTS.map((ep) => (
                  <tr key={ep.path} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                    <td className="py-2.5 px-4">
                      <span className={`text-xs font-mono font-medium ${
                        ep.method === "GET" ? "text-emerald-400" : "text-blue-400"
                      }`}>{ep.method}</span>
                    </td>
                    <td className="py-2.5 px-4">
                      <code className="text-xs text-slate-200">{ep.path}</code>
                    </td>
                    <td className="py-2.5 px-4 text-xs text-slate-500">{ep.desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {tab === "standards" && (
          <>
            <div className="glass-panel p-5">
              <h3 className="text-base font-semibold text-slate-100 mb-3">Fleet Documentation</h3>
              <div className="space-y-2">
                {FLEET_DOCS.map((d) => (
                  <a key={d.name} href={d.url} target="_blank" rel="noopener noreferrer"
                     className="block glass-panel p-3 hover:bg-slate-800/50 transition-colors group">
                    <div className="flex items-center justify-between mb-1">
                      <code className="text-sm text-fleet-400 group-hover:text-fleet-300">{d.name}</code>
                      <ExternalLink size={12} className="text-slate-600 group-hover:text-slate-400" />
                    </div>
                    <p className="text-xs text-slate-500">{d.desc}</p>
                  </a>
                ))}
              </div>
            </div>

            <div className="glass-panel p-5">
              <h3 className="text-base font-semibold text-slate-100 mb-3">Grade Interpretation</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                <div>
                  <h4 className="text-slate-300 font-medium mb-2">Glama (TDQS)</h4>
                  <ul className="space-y-1 text-slate-500">
                    <li><span className="text-emerald-400 font-bold">A</span> ≥ 3.5 — Passing</li>
                    <li><span className="text-blue-400 font-bold">B</span> ≥ 3.0 — Passing</li>
                    <li><span className="text-amber-400 font-bold">C</span> ≥ 2.0 — Acceptable target</li>
                    <li><span className="text-orange-400 font-bold">D</span> ≥ 1.0 — Below par</li>
                    <li><span className="text-red-400 font-bold">F</span> &lt; 1.0 — Failing</li>
                  </ul>
                </div>
                <div>
                  <h4 className="text-slate-300 font-medium mb-2">ToolBench</h4>
                  <ul className="space-y-1 text-slate-500">
                    <li><span className="text-emerald-400 font-bold">A+</span> 90-100</li>
                    <li><span className="text-emerald-400 font-bold">A</span> 80-89</li>
                    <li><span className="text-blue-400 font-bold">B</span> 70-79</li>
                    <li><span className="text-amber-400 font-bold">C</span> 60-69</li>
                    <li><span className="text-orange-400 font-bold">D</span> 50-59</li>
                    <li><span className="text-red-400 font-bold">F</span> &lt; 50</li>
                  </ul>
                </div>
              </div>
            </div>

            <div className="glass-panel p-5">
              <h3 className="text-base font-semibold text-slate-100 mb-3">TDQS Six Dimensions (Glama)</h3>
              <div className="space-y-2 text-xs">
                {[
                  ["Purpose Clarity", "25%", "First sentence states exactly what the tool does"],
                  ["Usage Guidelines", "20%", "When to call it, when not to, preconditions"],
                  ["Behavioral Transparency", "20%", "Returns, side effects, error conditions"],
                  ["Parameter Semantics", "15%", "Each param: type, allowed values, what it affects"],
                  ["Conciseness & Structure", "10%", "Not a wall of text, not a one-liner"],
                  ["Contextual Completeness", "10%", "Enough context without reading source"],
                ].map(([dim, weight, desc]) => (
                  <div key={dim} className="flex items-center gap-3">
                    <span className="w-36 text-slate-300 font-medium shrink-0">{dim}</span>
                    <span className="w-12 text-fleet-400 text-xs font-mono shrink-0">{weight}</span>
                    <span className="text-slate-500">{desc}</span>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
