import { Globe, CheckCircle, XCircle, ExternalLink } from "lucide-react";

const PLATFORMS = [
  {
    id: "toolbench",
    name: "ToolBench (Arcade.dev)",
    url: "https://toolbench.arcade.dev",
    reassess: true,
    methodology: "https://toolbench.arcade.dev/methodology",
    description: "Public methodology, letter grades A+ through F. Scores on definition quality (50%), protocol compliance (20%), supportability (30%). Submit button for rescoring after fixes.",
    notes: "Most detailed grading. Portmanteau tools penalized on 'verb-first naming' but FastMCP 3.2+ recognition improving.",
  },
  {
    id: "glama",
    name: "Glama.ai",
    url: "https://glama.ai/mcp/servers",
    reassess: false,
    methodology: "https://glama.ai/blog/2026-04-03-tool-definition-quality-score-tdqs",
    description: "TDQS (Tool Definition Quality Score) based on 6 dimensions: Purpose Clarity, Usage Guidelines, Behavioral Transparency, Parameter Semantics, Conciseness, Contextual Completeness. Auto-indexes from GitHub.",
    notes: "Scores 1-5 per dimension. Aggressive on description quality — 97% of tools fail at least one dimension.",
  },
  {
    id: "lobehub",
    name: "LobeHub Marketplace",
    url: "https://lobehub.com",
    reassess: false,
    methodology: null,
    description: "GitHub scrape marketplace. No grading — just presence/absence. Shallow scraper: reports zero tools for decorator-based MCP servers. Only parses README/PRD.",
    notes: "Distribution-only, no quality scoring. For discoverability, ensure README has clear tool table.",
  },
];

export default function Platforms() {
  return (
    <div>
      <h2 className="text-lg font-semibold text-slate-100 mb-6">Grading Platforms</h2>
      <div className="space-y-4">
        {PLATFORMS.map((p) => (
          <div key={p.id} className="bg-slate-900 border border-slate-800 rounded-lg p-5">
            <div className="flex items-start justify-between mb-2">
              <div>
                <h3 className="text-sm font-semibold text-slate-200">{p.name}</h3>
                <p className="text-xs text-slate-500 mt-0.5">{p.description}</p>
              </div>
              <a href={p.url} target="_blank" rel="noopener noreferrer" className="text-slate-500 hover:text-slate-300 flex-shrink-0">
                <ExternalLink size={14} />
              </a>
            </div>
            <div className="flex items-center gap-6 mt-3 text-xs">
              <div className="flex items-center gap-1.5">
                {p.reassess ? (
                  <CheckCircle size={12} className="text-emerald-500" />
                ) : (
                  <XCircle size={12} className="text-slate-600" />
                )}
                <span className="text-slate-400">Reassess API</span>
                <span className="text-slate-600">{p.reassess ? "Supported" : "Auto-indexed"}</span>
              </div>
              {p.methodology && (
                <a href={p.methodology} target="_blank" rel="noopener noreferrer" className="text-fleet-400 hover:text-fleet-300">
                  Methodology →
                </a>
              )}
            </div>
            <p className="mt-3 text-xs text-slate-600 italic">{p.notes}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
