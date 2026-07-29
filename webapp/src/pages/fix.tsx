import { useState } from "react";
import { useParams } from "react-router-dom";
import API_BASE from "../lib/api";

export default function FixPage() {
    const { repo: urlRepo } = useParams<{ repo: string }>();
    const [repo, setRepo] = useState(urlRepo || "");
    const [result, setResult] = useState<Record<string, any> | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    async function runScan(r?: string) {
        const target = r || repo;
        if (!target) return;
        setLoading(true);
        setError("");
        setResult(null);
        try {
            const res = await fetch(API_BASE + "/api/scraper/fix/" + encodeURIComponent(target), { method: "POST" });
            const j = await res.json();
            setResult(j);
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        }
        setLoading(false);
    }

    return (
        <div data-testid="fix-page" className="p-6 max-w-4xl mx-auto space-y-4">
            <h1 className="text-lg font-semibold text-slate-200">Fix Repo</h1>
            <div className="flex gap-2">
                <input
                    data-testid="fix-repo-input"
                    className="flex-1 bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-sm text-slate-200"
                    placeholder="repo-name (e.g. blender-mcp)"
                    value={repo}
                    onChange={(e) => setRepo(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && runScan()}
                />
                <button
                    data-testid="fix-scan-btn"
                    onClick={() => runScan()}
                    disabled={loading || !repo}
                    className="px-4 py-1.5 bg-amber-600 text-white rounded text-sm hover:bg-amber-500 disabled:opacity-50"
                >
                    {loading ? "Scanning..." : "Scan"}
                </button>
            </div>

            {error && <div className="text-red-400 text-sm">{error}</div>}

            {result && (
                <div className="space-y-3">
                    <div className="bg-slate-900 border border-slate-800 rounded-lg p-3">
                        <p className="text-sm text-slate-300">{result.message}</p>
                    </div>

                    {result.issues_used?.length > 0 && (
                        <div className="bg-slate-900 border border-slate-800 rounded-lg p-3">
                            <h2 className="text-sm font-semibold text-slate-300 mb-2">ToolBench Issues</h2>
                            <ul className="space-y-1">
                                {result.issues_used.map((issue: string, i: number) => (
                                    <li key={i} className="text-xs text-slate-400 leading-relaxed">{issue}</li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {Object.entries(result.fixes || {}).map(([type, data]) => {
                        const items: any[] = (data as any).details || [];
                        return (
                            <div key={type} className="bg-slate-900 border border-slate-800 rounded-lg p-3">
                                <h2 className="text-sm font-semibold text-slate-300 mb-2 capitalize">{type} ({items.length})</h2>
                                {items.length === 0 ? (
                                    <p className="text-xs text-slate-500">None found</p>
                                ) : (
                                    <table className="w-full text-xs">
                                        <thead>
                                            <tr className="text-slate-500 border-b border-slate-800">
                                                <th className="text-left py-1 pr-2">Function</th>
                                                <th className="text-left py-1">Detail</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {items.slice(0, 30).map((item: any, i: number) => (
                                                <tr key={i} className="border-b border-slate-800/50">
                                                    <td className="py-1 pr-2 text-slate-300 font-mono">{item.function}</td>
                                                    <td className="py-1 text-slate-400">
                                                        {item.current ? item.current.slice(0, 80) : `${item.parameter}: ${item.suggested}`}
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
