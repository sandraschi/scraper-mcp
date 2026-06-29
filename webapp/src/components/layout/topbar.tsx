import { useCapabilities } from "../../hooks/use-capabilities";

interface TopbarProps {
  label: string;
}

export function Topbar({ label }: TopbarProps) {
  const { caps } = useCapabilities();
  const tools = caps?.tool_surface?.total;

  return (
    <header className="h-12 border-b border-slate-800 flex items-center justify-between px-6 bg-slate-900/50 backdrop-blur">
      <h1 className="text-sm font-medium text-slate-300">{label}</h1>
      <div className="text-[11px] text-slate-500 font-mono">
        {caps?.server?.name ?? "scraper-mcp"}
        {tools != null ? ` · ${tools} tools` : ""}
        {caps?.features?.local_llm ? " · LLM" : ""}
      </div>
    </header>
  );
}
