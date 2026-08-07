import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { useCapabilities } from "../../hooks/use-capabilities";

// EXPERIMENTAL light mode (invert hack). Not fleet standard - see index.css.
// Toggling `.dark` off the root flips the invert filter; persisted so the
// choice survives reloads. Delete this + the CSS block to revert.
const THEME_KEY = "scraper-light-mode";

function useExperimentalTheme() {
  const [light, setLight] = useState(() => {
    try {
      return localStorage.getItem(THEME_KEY) === "1";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", !light);
    try {
      localStorage.setItem(THEME_KEY, light ? "1" : "0");
    } catch {
      // ignore storage errors
    }
  }, [light]);

  return { light, toggle: () => setLight((v) => !v) };
}

interface TopbarProps {
  label: string;
}

export function Topbar({ label }: TopbarProps) {
  const { caps } = useCapabilities();
  const tools = caps?.tool_surface?.total;
  const { light, toggle } = useExperimentalTheme();

  return (
    <header className="h-12 border-b border-slate-800 flex items-center justify-between px-6 bg-slate-900/50 backdrop-blur">
      <h1 className="text-sm font-medium text-slate-300">{label}</h1>
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={toggle}
          className="flex h-8 w-8 items-center justify-center rounded-md border border-slate-800 bg-slate-900/50 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
          title={light ? "Switch to dark (experimental light mode)" : "Switch to light (experimental, ugly)"}
          aria-label="Toggle light mode (experimental)"
        >
          {light ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
        </button>
        <div className="text-[11px] text-slate-500 font-mono">
          {caps?.server?.name ?? "scraper-mcp"}
          {tools != null ? ` · ${tools} tools` : ""}
          {caps?.features?.local_llm ? " · LLM" : ""}
        </div>
      </div>
    </header>
  );
}
