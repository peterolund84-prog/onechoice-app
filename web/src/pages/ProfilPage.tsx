import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { clearAuth, isLoggedIn, readAuth } from "../lib/auth";
import { getUserId, resetUserId } from "../lib/user";
import type { UserProfile } from "../lib/types";

function parseProfile(user: UserProfile): Record<string, unknown> {
  const raw = user.profile_json;
  if (raw && typeof raw === "object") return raw as Record<string, unknown>;
  if (typeof raw === "string") {
    try {
      return JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return {};
    }
  }
  return {};
}

export function ProfilPage() {
  const navigate = useNavigate();
  const [user, setUser] = useState<UserProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const auth = readAuth();

  const load = useCallback(async () => {
    try {
      const data = await api.me();
      setUser(data.user);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Kunde inte ladda profil");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const profile = user ? parseProfile(user) : {};
  const food = (profile.food as Record<string, unknown> | undefined) || {};
  // Default ON like Streamlit
  const showNutrition = food.show_nutrition !== false;
  const isPro = Boolean(user?.is_pro);
  const loggedIn = isLoggedIn() || Boolean(user && user.guest === false);

  async function togglePro() {
    setBusy(true);
    try {
      await api.patchMe({ is_pro: isPro ? 0 : 1 });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Kunde inte uppdatera");
    } finally {
      setBusy(false);
    }
  }

  async function toggleNutrition() {
    setBusy(true);
    try {
      const next = {
        ...profile,
        food: { ...food, show_nutrition: !showNutrition },
      };
      await api.patchMe({ profile_json: next });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Kunde inte uppdatera");
    } finally {
      setBusy(false);
    }
  }

  async function onExport() {
    setBusy(true);
    try {
      const data = await api.exportMe();
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `onechoice-export-${getUserId()}.json`;
      a.click();
      URL.revokeObjectURL(url);
      setMsg("Export nedladdad");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export misslyckades");
    } finally {
      setBusy(false);
    }
  }

  async function onDelete() {
    if (!window.confirm("Radera allt för den här användaren?")) return;
    setBusy(true);
    try {
      await api.deleteMe();
      clearAuth();
      resetUserId();
      setMsg("Konto raderat");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Radering misslyckades");
    } finally {
      setBusy(false);
    }
  }

  async function onLogout() {
    setBusy(true);
    try {
      await api.logout();
    } catch {
      /* ignore */
    }
    clearAuth();
    setMsg("Utloggad");
    setBusy(false);
    navigate("/login");
  }

  return (
    <section className="oc-page">
      <h1 className="oc-page-title">Profil</h1>
      <p className="oc-page-sub">
        {loggedIn
          ? auth?.email || user?.email || "Inloggad"
          : "Gäst / lokal demo"}
      </p>
      {!loggedIn ? <p className="oc-mono">{getUserId()}</p> : null}

      <div className="oc-stack">
        {!loggedIn ? (
          <button
            type="button"
            className="oc-cta"
            disabled={busy}
            onClick={() => navigate("/login")}
          >
            Logga in / Skapa konto
          </button>
        ) : (
          <button
            type="button"
            className="oc-btn oc-btn-ghost"
            disabled={busy}
            onClick={onLogout}
          >
            Logga ut
          </button>
        )}
        <button type="button" className="oc-btn" disabled={busy} onClick={togglePro}>
          {isPro ? "Pro: på (demo)" : "Aktivera Pro (demo)"}
        </button>
        <button
          type="button"
          className="oc-btn oc-btn-ghost"
          disabled={busy}
          onClick={toggleNutrition}
        >
          Näringsinfo: {showNutrition ? "på" : "av"}
        </button>
        <button type="button" className="oc-btn oc-btn-ghost" disabled={busy} onClick={onExport}>
          Exportera mina data (GDPR)
        </button>
        <button type="button" className="oc-btn oc-btn-danger" disabled={busy} onClick={onDelete}>
          Radera konto
        </button>
      </div>

      {msg ? <p className="oc-ok">{msg}</p> : null}
      {error ? <p className="oc-error">{error}</p> : null}
    </section>
  );
}
