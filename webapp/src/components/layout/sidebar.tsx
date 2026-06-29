import { useState } from "react";
import { NavLink } from "react-router-dom";
import { LayoutDashboard, Radio, BarChart3, Wrench, ScrollText, Grid3X3, HelpCircle, Settings } from "lucide-react";

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("scraper-sidebar") === "1");

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem("scraper-sidebar", next ? "1" : "0");
  };

  const links = [
    { to: "/", icon: LayoutDashboard, label: "Home" },
    { to: "/tools", icon: Wrench, label: "Tools" },
    { to: "/apps", icon: Grid3X3, label: "Apps" },
    { to: "/settings", icon: Settings, label: "Settings" },
    { to: "/help", icon: HelpCircle, label: "Help" },
    { to: "/logs", icon: ScrollText, label: "Logs" },
    { to: "/platforms", icon: Radio, label: "Platforms" },
  ];

  return (
    <aside className={`bg-slate-900 border-r border-slate-800 flex flex-col transition-all ${collapsed ? "w-14" : "w-52"}`}>
      <div className="flex items-center justify-between p-3 border-b border-slate-800">
        {!collapsed && (
          <span className="text-sm font-semibold text-fleet-400 flex items-center gap-2">
            <BarChart3 size={16} /> Scraper
          </span>
        )}
        <button onClick={toggle} className="text-slate-500 hover:text-slate-300 text-xs">
          {collapsed ? ">" : "<"}
        </button>
      </div>
      <nav className="flex-1 py-2">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 text-sm transition-colors ${
                isActive ? "bg-fleet-700/20 text-fleet-400 border-r-2 border-fleet-500" : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
              }`
            }
            title={label}
          >
            <Icon size={16} />
            {!collapsed && <span>{label}</span>}
          </NavLink>
        ))}
      </nav>
      <div className="p-3 border-t border-slate-800 text-[10px] text-slate-600">
        {!collapsed && "scraper-mcp v0.2"}
      </div>
    </aside>
  );
}
