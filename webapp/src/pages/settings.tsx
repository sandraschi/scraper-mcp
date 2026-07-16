import API_BASE from "@/lib/api";
import { useEffect, useState } from "react";
import { useCapabilities } from "../hooks/use-capabilities";

type LocalLlm = {
  ollama: { ok?: boolean; error?: string } | null;
  lm_studio: { ok?: boolean; error?: string } | null;
};

export default function SettingsPage() {
  const { caps, error: capsError, reload } = useCapabilities();
  const [local, setLocal] = useState<LocalLlm | null>(null);

  useEffect(() => {
    fetch(API_BASE + "/api/meta/local-llm")
      .then((r) => r.json())
      .then((j) => setLocal(j as LocalLlm))
      .catch(() => setLocal(null));
  }, []);

  return (
    <div data-testid="settings" className="max-w-2xl space-y-4">
      <h2 className="text-lg font-semibold text-slate-100">Settings</h2>

      <section className="glass-panel p-4">
        <h3 className="text-sm font-medium text-slate-200 mb-2">Server capabilities</h3>
        {capsError && <p className="text-xs text-red-400">{capsError}</p>}
        {caps && (
          <dl className="text-xs text-slate-400 grid grid-cols-2 gap-2">
            <dt>Service</dt>
            <dd>{caps.server?.name} v{caps.server?.version}</dd>
            <dt>Tools</dt>
            <dd>{caps.tool_surface?.total ?? 0}</dd>
            <dt>FastMCP</dt>
            <dd>{caps.server?.fastmcp ?? "—"}</dd>
          </dl>
        )}
        <button type="button" className="btn btn-secondary mt-3" onClick={() => void reload()}>
          Reload capabilities
        </button>
      </section>

      <section className="glass-panel p-4">
        <h3 className="text-sm font-medium text-slate-200 mb-2">Local LLM (Glom On)</h3>
        <ul className="text-xs text-slate-400 space-y-1">
          <li>Ollama (11434): {local?.ollama?.ok ? "reachable" : local?.ollama?.error ?? "unreachable"}</li>
          <li>LM Studio (1234): {local?.lm_studio?.ok ? "reachable" : local?.lm_studio?.error ?? "unreachable"}</li>
        </ul>
      </section>

      <section className="glass-panel p-4 text-xs text-slate-500">
        <p>
          Fleet registry path: <code>SCRAPER_FLEET_REGISTRY</code> env or default{" "}
          <code>D:\Dev\repos\mcp-central-docs\operations\fleet-registry.json</code>
        </p>
      </section>
    </div>
  );
}
