import { BrowserRouter, Navigate, Routes, Route } from "react-router-dom";
import { AppLayout } from "./components/layout/app-layout";
import { LoggerProvider } from "./context/logger-context";
import Dashboard from "./pages/dashboard";
import RepoDetail from "./pages/repo-detail";
import Platforms from "./pages/platforms";
import ToolsPage from "./pages/tools";
import LogsPage from "./pages/logs";
import AppsPage from "./pages/apps";
import HelpPage from "./pages/help";
import SettingsPage from "./pages/settings";
import FloatingChat from "./components/FloatingChat";
import { useZoom } from "./lib/use-zoom";

export default function App() {
  useZoom();
  return (
    <LoggerProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/repo/:repoName" element={<RepoDetail />} />
            <Route path="/platforms" element={<Platforms />} />
            <Route path="/tools" element={<ToolsPage />} />
            <Route path="/logs" element={<LogsPage />} />
            <Route path="/apps" element={<AppsPage />} />
            <Route path="/help" element={<HelpPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
        <FloatingChat />
      </BrowserRouter>
    </LoggerProvider>
  );
}
