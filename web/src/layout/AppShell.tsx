import { Outlet } from "react-router-dom";
import { BottomNav } from "../components/BottomNav";

export function AppShell() {
  return (
    <div className="oc-app">
      <div className="oc-fiber" aria-hidden="true" />
      <header className="oc-header">
        <div className="oc-wordmark">OneChoice</div>
      </header>
      <main className="oc-main">
        <Outlet />
      </main>
      <BottomNav />
    </div>
  );
}
