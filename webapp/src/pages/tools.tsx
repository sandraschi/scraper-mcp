import API_BASE from "@/lib/api";
import { useCallback, useEffect, useState } from "react";
import { useLogger } from "../context/logger-context";

const DEFAULT_SEARCH =
  "https://toolbench.arcade.dev/?q=sandraschi&status=SCORED";

type ScraperStatus = {
  script_path: string;
  script_exists: boolean;
  playwright_available: boolean;
  output_root: string;
  hint: string;
};

type MetaTool = {
  name: string;
  description: string;
  risk?: string;
  operations?: string[];
};

export default function ToolsPage() {
  const { append } = useLogger();
  const [metaTools, setMetaTools] = useState<MetaTool[]>([]);
  const [status, setStatus] = useState<ScraperStatus | null>(null);
  const [outSubdir, setOutSubdir] = useState("default");
  const [searchUrl, setSearchUrl] = useState(DEFAULT_SEARCH);
  const [maxPages, setMaxPages] = useState(15);
  const [delaySec, setDelaySec] = useState(3);
  const [jitterSec, setJitterSec] = useState(2);
  const [headed, setHeaded] = useState(false);
  const [saveHtml, setSaveHtml] = useState(false);
  const [urlsText, setUrlsText] = useState(
    "https://toolbench.arcade.dev/tools/cmmiudisr04w1fqqwpdizyebc\n",
  );
  const [log, setLog] = useState("");
  const [busy, setBusy] = useState(false);
  const [files, setFiles] = useState<{ path: string; size: number }[]>([]);
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [previewContent, setPreviewContent] = useState("");

  const refreshStatus = useCallback(() => {
    fetch(API_BASE + "/api/scraper/status")
      .then((r) => r.json())
      .then((j) => setStatus(j as ScraperStatus))
      .catch(() => setStatus(null));
  }, []);

  const refreshTree = useCallback(() => {
    const q = new URLSearchParams({ subdir: outSubdir });
    fetch(`${API_BASE}/api/scraper/tree?${q}`)
      .then((r) => r.json())
      .then((j) => setFiles(j.files ?? []))
      .catch(() => setFiles([]));
  }, [outSubdir]);

  useEffect(() => {
    fetch(API_BASE + "/api/tools")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((j) => {
        const live = ((j.tools as { name: string; description?: string }[]) ?? []).map((t) => ({
          name: t.name,
          description: t.description ?? "",
          risk: "mcp",
          operations: [] as string[],
        }));
        if (live.length > 0) {
          setMetaTools(live);
          append("INFO", `Loaded ${live.length} tools from /api/tools`);
          return;
        }
        return fetch(API_BASE + "/api/meta/tools")
          .then((r2) => r2.json())
          .then((j2) => {
            setMetaTools((j2.tools as MetaTool[]) ?? []);
            append("INFO", "Loaded MCP tool manifest (meta fallback)");
          });
      })
      .catch(() => append("ERROR", "Failed to load /api/tools — is backend on :10998 running?"));
    refreshStatus();
  }, [append, refreshStatus]);

  useEffect(() => {
    refreshTree();
  }, [refreshTree, outSubdir]);

  async function runPost(path: string, body: Record<string, unknown>, label: string) {
    setBusy(true);
    setLog("");
    append("INFO", `${label}…`);
    try {
      const r = await fetch(API_BASE + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      const text = JSON.stringify(j, null, 2);
      setLog(text);
      if (j.success) append("INFO", `${label} completed (exit 0)`);
      else append("ERROR", `${label} failed: ${JSON.stringify(j).slice(0, 400)}`);
      refreshTree();
    } catch (e) {
      const msg = String(e);
      setLog(msg);
      append("ERROR", `${label}: ${msg}`);
    } finally {
      setBusy(false);
    }
  }

  async function loadPreview(path: string) {
    setPreviewPath(path);
    setPreviewContent("…");
    append("DEBUG", `Preview ${path}`);
    try {
      const r = await fetch(
        `${API_BASE}/api/scraper/file?rel_path=${encodeURIComponent(path)}`,
      );
      const j = await r.json();
      setPreviewContent(j.content ?? JSON.stringify(j));
    } catch (e) {
      setPreviewContent(String(e));
    }
  }

  return (
    <div>
      <h1 style={{ fontSize: "1.5rem", marginTop: 0 }}>MCP Inspector</h1>
      <p style={{ color: "var(--muted)" }}>
        MCP tools + ToolBench Playwright page archiver. Coverage matrix is on{" "}
        <a href="/">Dashboard</a>; Glama/LobeHub grades via <code>scraper_refresh</code>.
      </p>

      <div className="glass-panel" style={{ padding: "1rem", marginBottom: "1rem" }}>
        <h2 style={{ fontSize: "1rem", marginTop: 0 }}>Tools</h2>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.88rem" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border)" }}>
              <th style={{ padding: "0.35rem" }}>Name</th>
              <th style={{ padding: "0.35rem" }}>Risk</th>
              <th style={{ padding: "0.35rem" }}>Operations</th>
            </tr>
          </thead>
          <tbody>
            {metaTools.map((t) => (
              <tr key={t.name} style={{ borderBottom: "1px solid var(--border)" }}>
                <td style={{ padding: "0.45rem", fontFamily: "monospace" }}>{t.name}</td>
                <td style={{ padding: "0.45rem" }}>{t.risk ?? "—"}</td>
                <td style={{ padding: "0.45rem" }}>{(t.operations ?? []).join(", ") || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p style={{ fontSize: "0.8rem", color: "var(--muted)", marginBottom: 0 }}>
          Source: <code>/api/tools</code> (live MCP) — HTTP MCP at <code>/mcp</code> on port 10998.
        </p>
      </div>

      <div className="glass-panel" style={{ padding: "1rem" }}>
        <h2 style={{ fontSize: "1rem", marginTop: 0 }}>Playwright scraper</h2>
        {status && (
          <div style={{ fontSize: "0.85rem", opacity: 0.95, marginBottom: "1rem" }}>
            <div>
              Script: <code>{status.script_path}</code> —{" "}
              {status.script_exists ? "found" : "missing"}
            </div>
            <div>
              Playwright: {status.playwright_available ? "ok" : "not installed — " + status.hint}
            </div>
            <div>
              Output: <code>{status.output_root}</code>
            </div>
          </div>
        )}
        <label style={{ display: "block", marginBottom: "0.5rem" }}>
          Output subfolder
          <input
            className="input"
            value={outSubdir}
            onChange={(e) => setOutSubdir(e.target.value)}
            style={{ display: "block", marginTop: 6, maxWidth: 520 }}
          />
        </label>

        <h3 style={{ fontSize: "0.95rem" }}>Discover</h3>
        <textarea
          className="textarea"
          value={searchUrl}
          onChange={(e) => setSearchUrl(e.target.value)}
          rows={2}
        />
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 8 }}>
          <label>
            max pages{" "}
            <input
              type="number"
              min={1}
              max={100}
              value={maxPages}
              onChange={(e) => setMaxPages(Number(e.target.value))}
              style={{ width: 70 }}
            />
          </label>
          <label>
            delay s{" "}
            <input
              type="number"
              step={0.5}
              value={delaySec}
              onChange={(e) => setDelaySec(Number(e.target.value))}
              style={{ width: 70 }}
            />
          </label>
          <label>
            jitter s{" "}
            <input
              type="number"
              step={0.5}
              value={jitterSec}
              onChange={(e) => setJitterSec(Number(e.target.value))}
              style={{ width: 70 }}
            />
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <input type="checkbox" checked={headed} onChange={(e) => setHeaded(e.target.checked)} />
            headed
          </label>
        </div>
        <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 8 }}>
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={() =>
              runPost(
                "/api/scraper/discover",
                {
                  search_url: searchUrl,
                  out_subdir: outSubdir,
                  max_pages: maxPages,
                  delay_seconds: delaySec,
                  jitter_seconds: jitterSec,
                  headed,
                },
                "discover",
              )
            }
          >
            Run discover
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            style={{ background: "hsl(260 45% 42%)" }}
            onClick={() =>
              runPost(
                "/api/scraper/full",
                {
                  search_url: searchUrl,
                  out_subdir: outSubdir,
                  max_pages: maxPages,
                  delay_seconds: Math.max(delaySec, 4),
                  jitter_seconds: jitterSec,
                  save_html: saveHtml,
                  headed,
                },
                "full",
              )
            }
          >
            Run full
          </button>
        </div>

        <h3 style={{ fontSize: "0.95rem", marginTop: "1.25rem" }}>Scrape URLs</h3>
        <textarea
          className="textarea"
          value={urlsText}
          onChange={(e) => setUrlsText(e.target.value)}
          rows={5}
        />
        <label style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 8 }}>
          <input type="checkbox" checked={saveHtml} onChange={(e) => setSaveHtml(e.target.checked)} />
          save gzip HTML
        </label>
        <button
          type="button"
          className="btn btn-primary"
          style={{ marginTop: 10, background: "hsl(142 35% 36%)" }}
          disabled={busy}
          onClick={() =>
            runPost(
              "/api/scraper/scrape",
              {
                urls_text: urlsText,
                out_subdir: outSubdir,
                delay_seconds: delaySec,
                jitter_seconds: jitterSec,
                save_html: saveHtml,
                headed,
              },
              "scrape",
            )
          }
        >
          Run scrape
        </button>

        <h3 style={{ fontSize: "0.95rem", marginTop: "1rem" }}>Last response</h3>
        <pre
          style={{
            fontSize: "0.72rem",
            overflow: "auto",
            maxHeight: 220,
            padding: 12,
            background: "hsl(220 18% 7%)",
            borderRadius: 8,
            border: "1px solid var(--border)",
          }}
        >
          {log || "(output)"}
        </pre>

        <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button type="button" className="btn btn-secondary" onClick={() => refreshTree()}>
            Refresh file list
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            style={{ borderColor: "hsl(0 50% 40%)" }}
            onClick={() => {
              if (confirm(`Clear "${outSubdir}"?`))
                fetch(`${API_BASE}/api/scraper/output?subdir=${encodeURIComponent(outSubdir)}`, {
                  method: "DELETE",
                }).then(() => {
                  refreshTree();
                  append("SOTA-WARN", `Cleared output subdir ${outSubdir}`);
                });
            }}
          >
            Clear subfolder
          </button>
        </div>

        <ul style={{ listStyle: "none", padding: 0, marginTop: 12, maxHeight: 280, overflow: "auto" }}>
          {files.map((f) => (
            <li key={f.path} style={{ marginBottom: 6, fontSize: "0.82rem" }}>
              <button
                type="button"
                style={{ background: "none", border: "none", color: "var(--accent)", cursor: "pointer", padding: 0 }}
                onClick={() => loadPreview(f.path)}
              >
                {f.path}
              </button>
              <span style={{ opacity: 0.6 }}> ({f.size} B)</span>
            </li>
          ))}
        </ul>

        {previewPath && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: "0.85rem", color: "var(--muted)" }}>{previewPath}</div>
            <pre
              style={{
                fontSize: "0.7rem",
                overflow: "auto",
                maxHeight: 200,
                padding: 12,
                background: "hsl(220 18% 7%)",
                borderRadius: 8,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {previewContent}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
