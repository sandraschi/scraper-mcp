import API_BASE from "../lib/api";
import { useEffect, useState } from "react";
import { useCapabilities } from "../hooks/use-capabilities";

type ProviderProbe = {
  name: string;
  port: number;
  base: string;
  status: "probing" | "detected" | "not_found";
};

const PROVIDERS: Omit<ProviderProbe, "status">[] = [
  { name: "Ollama", port: 11434, base: "http://localhost:11434" },
  { name: "LM Studio", port: 1234, base: "http://localhost:1234" },
  { name: "vLLM", port: 8000, base: "http://localhost:8000" },
];

async function probeProvider(base: string, port: number): Promise<boolean> {
  try {
    const r = await fetch(`${base}/api/tags`, { signal: AbortSignal.timeout(3000) });
    return r.ok;
  } catch {
    try {
      const r = await fetch(`${base}/v1/models`, { signal: AbortSignal.timeout(3000) });
      return r.ok;
    } catch {
      return false;
    }
  }
}

async function fetchModels(base: string, port: number): Promise<string[]> {
  try {
    const r = await fetch(`${base}/api/tags`, { signal: AbortSignal.timeout(3000) });
    if (r.ok) {
      const j = await r.json();
      return (j.models || []).map((m: any) => m.name);
    }
  } catch { /* try next */ }
  try {
    const r = await fetch(`${base}/v1/models`, { signal: AbortSignal.timeout(3000) });
    if (r.ok) {
      const j = await r.json();
      return (j.data || []).map((m: any) => m.id);
    }
  } catch { /* not found */ }
  return [];
}

const LS_PROVIDER = "llm_provider";
const LS_MODEL = "llm_model";

export default function SettingsPage() {
  const { caps, error: capsError, reload } = useCapabilities();
  const [probes, setProbes] = useState<ProviderProbe[]>(
    PROVIDERS.map((p) => ({ ...p, status: "probing" }))
  );
  const [selectedProvider, setSelectedProvider] = useState(() => {
    try { return localStorage.getItem(LS_PROVIDER) || ""; } catch { return ""; }
  });
  const [selectedModel, setSelectedModel] = useState(() => {
    try { return localStorage.getItem(LS_MODEL) || ""; } catch { return ""; }
  });
  const [availableModels, setAvailableModels] = useState<string[]>([]);

  // Probe providers on mount
  useEffect(() => {
    (async () => {
      const results = await Promise.all(
        PROVIDERS.map(async (p) => ({
          ...p,
          status: (await probeProvider(p.base, p.port)) ? "detected" as const : "not_found" as const,
        }))
      );
      setProbes(results);
    })();
  }, []);

  // When selected provider changes, fetch models
  useEffect(() => {
    if (!selectedProvider) return;
    const prov = probes.find((p) => p.name === selectedProvider);
    if (!prov || prov.status !== "detected") return;
    (async () => {
      const models = await fetchModels(prov.base, prov.port);
      setAvailableModels(models);
      // Restore saved model if still valid
      const saved = localStorage.getItem(LS_MODEL);
      if (saved && models.includes(saved)) {
        setSelectedModel(saved);
      } else if (models.length > 0) {
        setSelectedModel(models[0]);
      }
    })();
  }, [selectedProvider, probes]);

  function handleProviderChange(name: string) {
    setSelectedProvider(name);
    setSelectedModel("");
    setAvailableModels([]);
    localStorage.setItem(LS_PROVIDER, name);
  }

  function handleModelChange(model: string) {
    setSelectedModel(model);
    localStorage.setItem(LS_MODEL, model);
  }

  const detectedProviders = probes.filter((p) => p.status === "detected");
  const anyProbing = probes.some((p) => p.status === "probing");

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
            <dd>{caps.server?.fastmcp ?? "\u2014"}</dd>
          </dl>
        )}
        <button type="button" className="btn btn-secondary mt-3" onClick={() => void reload()}>
          Reload capabilities
        </button>
      </section>

      <section className="glass-panel p-4">
        <h3 className="text-sm font-medium text-slate-200 mb-2">Local LLM Provider</h3>

        {/* Probe status */}
        <div className="text-xs text-slate-400 space-y-1 mb-3">
          {probes.map((p) => (
            <div key={p.name} className="flex items-center gap-2">
              <span
                className={`w-2 h-2 rounded-full ${
                  p.status === "detected" ? "bg-green-500" :
                  p.status === "probing" ? "bg-amber-500 animate-pulse" :
                  "bg-slate-600"
                }`}
              />
              <span className={p.status === "detected" ? "text-slate-300" : "text-slate-500"}>
                {p.name} (: {p.port})
                {p.status === "detected" ? " Detected" : p.status === "probing" ? " Probing..." : " Not found"}
              </span>
            </div>
          ))}
        </div>

        {/* Provider dropdown */}
        <div className="mb-3">
          <label className="text-xs text-slate-400 block mb-1">Provider</label>
          <select
            data-testid="llm-provider-select"
            className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200"
            value={selectedProvider}
            onChange={(e) => handleProviderChange(e.target.value)}
            disabled={anyProbing}
          >
            {detectedProviders.length === 0 ? (
              <option value="" disabled>No local LLM detected</option>
            ) : (
              <>
                <option value="">-- Select --</option>
                {detectedProviders.map((p) => (
                  <option key={p.name} value={p.name}>{p.name} (: {p.port})</option>
                ))}
              </>
            )}
          </select>
        </div>

        {/* Model dropdown */}
        {selectedProvider && (
          <div>
            <label className="text-xs text-slate-400 block mb-1">Model</label>
            <select
              data-testid="llm-model-select"
              className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200"
              value={selectedModel}
              onChange={(e) => handleModelChange(e.target.value)}
            >
              {availableModels.length === 0 ? (
                <option value="" disabled>No models found</option>
              ) : (
                availableModels.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))
              )}
            </select>
          </div>
        )}

        {detectedProviders.length === 0 && !anyProbing && (
          <p className="text-xs text-amber-500 mt-2">
            Install{" "}
            <a href="https://ollama.com" className="underline" target="_blank" rel="noopener">Ollama</a>{" "}
            or{" "}
            <a href="https://lmstudio.ai" className="underline" target="_blank" rel="noopener">LM Studio</a>{" "}
            to enable AI features.
          </p>
        )}
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
