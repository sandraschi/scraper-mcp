import { useState } from "react";
import { useLogger } from "../context/logger-context";

export function LoggerPanel() {
  const { lines } = useLogger();
  const [open, setOpen] = useState(false);

  return (
    <div className="border-t border-slate-800 bg-slate-950/95 shrink-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2 text-xs text-slate-400 hover:text-slate-200 hover:bg-slate-900/80"
      >
        <span>Event log ({lines.length})</span>
        <span>{open ? "▼" : "▲"}</span>
      </button>
      {open && (
        <pre className="max-h-40 overflow-auto px-4 pb-3 text-[11px] text-slate-400 font-mono whitespace-pre-wrap">
          {lines.length === 0 ? "No events yet." : lines.join("\n")}
        </pre>
      )}
    </div>
  );
}
