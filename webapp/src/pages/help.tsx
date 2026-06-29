export default function HelpPage() {
  return (
    <div className="max-w-3xl space-y-4 text-sm text-slate-300">
      <h2 className="text-lg font-semibold text-slate-100">Help</h2>
      <section className="glass-panel p-4 space-y-2">
        <h3 className="font-medium text-slate-100">Quick start</h3>
        <ol className="list-decimal list-inside space-y-1 text-slate-400">
          <li>Run <code className="text-fleet-400">webapp\start.bat</code> — frontend <strong>10999</strong>, backend <strong>10998</strong>.</li>
          <li>Open <strong>Coverage</strong> — fleet repos load from <code>mcp-central-docs/operations/fleet-registry.json</code>.</li>
          <li>Click <strong>Refresh All</strong> to pull ToolBench / Glama / LobeHub grades (remote APIs may return 0; matrix still lists fleet repos).</li>
          <li>Use <strong>Tools</strong> for MCP inspector + ToolBench Playwright archiver.</li>
        </ol>
      </section>
      <section className="glass-panel p-4 space-y-2">
        <h3 className="font-medium text-slate-100">Endpoints</h3>
        <ul className="font-mono text-xs text-slate-400 space-y-1">
          <li>GET /api/capabilities</li>
          <li>GET /api/tools</li>
          <li>GET /api/coverage</li>
          <li>POST /api/refresh</li>
          <li>MCP HTTP /mcp</li>
        </ul>
      </section>
      <section className="glass-panel p-4">
        <p className="text-slate-400">
          Replaces toolbench-mcp (10816/10817). See repo <code>README.md</code> and{" "}
          <code>mcp-central-docs/operations/WEBAPP_PORTS.md</code> (10998/10999).
        </p>
      </section>
    </div>
  );
}
