import { Outlet, useLocation } from "react-router-dom";
import { LoggerPanel } from "../logger-panel";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";

export function AppLayout() {
  const location = useLocation();

  const labels: Record<string, string> = {
    "/": "Coverage Matrix",
    "/tools": "MCP Tools",
    "/apps": "Fleet Apps",
    "/settings": "Settings",
    "/help": "Help",
    "/logs": "Logs",
    "/platforms": "Platforms",
  };
  if (location.pathname.startsWith("/repo/")) {
    labels[location.pathname] = decodeURIComponent(location.pathname.split("/")[2] || "");
  }

  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Topbar label={labels[location.pathname] || "Scraper MCP"} />
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
        <LoggerPanel />
      </div>
    </div>
  );
}
