import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
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
  const [user, setUser] = useState<UserProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

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
  const showNutrition = Boolean(food.show_nutrition);
  const isPro = Boolean(user?.is_pro);

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
    if (!window.confirm("Radera allt lokalt för den här gästen?")) return;
    setBusy(true);
    try {
      await api.deleteMe();
      resetUserId();
      setMsg("Konto raderat — ny gäst-id skapad");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Radering misslyckades");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="oc-page">
      <h1 className="oc-page-title">Profil</h1>
      <p className="oc-page-sub">
        {user?.guest !== false ? "Gäst / lokal demo" : "Inloggad"}
      </p>
      <p className="oc-mono">{getUserId()}</p>

      <div className="oc-stack">
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

      <p className="oc-page-sub" style={{ marginTop: 24 }}>
        Supabase-login kommer i nästa steg. Tills dess sparas allt lokalt via gäst-id.
      </p>

      {msg ? <p className="oc-ok">{msg}</p> : null}
      {error ? <p className="oc-error">{error}</p> : null}
    </section>
  );
}
