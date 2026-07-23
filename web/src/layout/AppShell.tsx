import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { BottomNav } from "../components/BottomNav";
import { api } from "../lib/api";

function displayNameFromUser(user: Record<string, unknown> | null): string | null {
  if (!user) return null;
  if (user.guest) return null;
  const profile = user.profile_json;
  if (profile && typeof profile === "object") {
    const p = profile as Record<string, unknown>;
    for (const key of ["display_name", "name", "full_name", "first_name"]) {
      const v = p[key];
      if (typeof v === "string" && v.trim()) return v.trim();
    }
  }
  if (typeof user.email === "string" && user.email.includes("@")) {
    return user.email.split("@")[0] || null;
  }
  return null;
}

export function AppShell() {
  const [name, setName] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .me()
      .then((data) => {
        if (cancelled) return;
        setName(displayNameFromUser(data.user as Record<string, unknown>));
      })
      .catch(() => {
        /* guest / offline */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="oc-app">
      <div className="oc-fiber" aria-hidden="true" />
      <header className="oc-header">
        <div className="oc-wordmark">OneChoice</div>
        {name ? <div className="oc-header-user">{name}</div> : null}
      </header>
      <main className="oc-main">
        <Outlet />
      </main>
      <BottomNav />
    </div>
  );
}
