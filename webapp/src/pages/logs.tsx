import API_BASE from "@/lib/api";
import { useCallback, useEffect, useState } from "react";
import { useLogger } from "../context/logger-context";

type LogEntry = {
  id: string;
  timestamp: string;
  level: string;
  kind: string;
  detail: string;
};

type LogResponse = {
  entries: LogEntry[];
  total: number;
  limit: number;
  offset: number;
  max_entries: number;
};

export default function LogsPage() {
  const { append } = useLogger();
  const [data, setData] = useState<LogResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [level, setLevel] = useState("");
  const [search, setSearch] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: "100", sort: "desc" });
      if (level) params.set("level", level);
      if (search.trim()) params.set("search", search.trim());
      const r = await fetch(`${API_BASE}/api/logs?${params}`);
      const j = (await r.json()) as LogResponse;
      setData(j);
      append("INFO", `Loaded ${j.entries.length} log entries`);
    } catch (e) {
      append("ERROR", `Logs fetch failed: ${String(e)}`);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [append, level, search]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const exportLogs = async () => {
    try {
      const r = await fetch(API_BASE + "/api/logs/export?format=json");
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "scraper-mcp-logs.json";
      a.click();
      URL.revokeObjectURL(url);
      append("INFO", "Exported logs JSON");
    } catch (e) {
      append("ERROR", String(e));
    }
  };

  const clearLogs = async () => {
    try {
      await fetch(API_BASE + "/api/logs", { method: "DELETE" });
      append("INFO", "Log buffer cleared");
      await refresh();
    } catch (e) {
      append("ERROR", String(e));
    }
  };

  return (
    <div>
      <h1 style={{ fontSize: "1.5rem", marginTop: 0 }}>Event Logs</h1>
      <p style={{ color: "var(--muted)", lineHeight: 1.55 }}>
        Fleet ring buffer at <code>/api/logs</code> — WEBAPP_LOGS_PAGE.md v1.0.
      </p>

      <div className="glass-panel" style={{ padding: "1rem", marginBottom: "1rem", display: "flex", gap: 12, flexWrap: "wrap" }}>
        <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
          Level
          <select className="input" value={level} onChange={(e) => setLevel(e.target.value)} style={{ maxWidth: 140 }}>
            <option value="">All</option>
            <option value="DEBUG">DEBUG</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
          </select>
        </label>
        <input
          className="input"
          placeholder="Search detail / meta"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ flex: "1 1 200px", minWidth: 180 }}
        />
        <button type="button" className="btn btn-secondary" onClick={() => void refresh()}>
          Refresh
        </button>
        <button type="button" className="btn btn-secondary" onClick={() => void exportLogs()}>
          Export JSON
        </button>
        <button type="button" className="btn btn-secondary" onClick={() => void clearLogs()}>
          Clear
        </button>
      </div>

      {data && (
        <div style={{ fontSize: "0.8rem", color: "var(--muted)", marginBottom: 8 }}>
          {data.total} entries (max {data.max_entries})
        </div>
      )}

      <div className="glass-panel" style={{ padding: "1rem", fontFamily: "monospace", fontSize: "0.75rem", maxHeight: "60vh", overflowY: "auto" }}>
        {loading ? (
          <div className="skeleton" style={{ height: 120 }} />
        ) : !data?.entries.length ? (
          <div style={{ color: "var(--muted)" }}>No log entries yet.</div>
        ) : (
          data.entries.map((e) => (
            <div key={e.id} style={{ display: "flex", gap: 12, marginBottom: 6, flexWrap: "wrap" }}>
              <span style={{ color: "var(--muted)", minWidth: 180 }}>{e.timestamp}</span>
              <span style={{ color: e.level === "ERROR" ? "#f87171" : "#34d399", minWidth: 64 }}>{e.level}</span>
              <span style={{ color: "#94a3b8", minWidth: 72 }}>{e.kind}</span>
              <span style={{ color: "#e2e8f0" }}>{e.detail}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
