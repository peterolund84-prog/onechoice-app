import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { clearAuth, writeAuth } from "../lib/auth";
import { getUserId } from "../lib/user";

export function AuthPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    api
      .authStatus()
      .then((s) => setConfigured(Boolean(s.configured)))
      .catch(() => setConfigured(false));
  }, []);

  function continueGuest() {
    clearAuth();
    void getUserId();
    navigate("/");
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!configured) return;
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      if (mode === "login") {
        const sess = await api.login(email.trim(), password);
        writeAuth({
          user_id: sess.user_id,
          email: sess.email,
          access_token: sess.access_token,
          refresh_token: sess.refresh_token,
        });
        navigate("/");
        return;
      }
      if (!consent) {
        setError("Du måste acceptera integritetspolicyn.");
        return;
      }
      const sess = await api.signup(email.trim(), password, true);
      if (sess.access_token && sess.refresh_token && sess.user_id) {
        writeAuth({
          user_id: sess.user_id,
          email: sess.email,
          access_token: sess.access_token,
          refresh_token: sess.refresh_token,
        });
        navigate("/");
        return;
      }
      setMsg("Konto skapat. Bekräfta e-post om det krävs, sedan logga in.");
      setMode("login");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Inloggning misslyckades");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="oc-page">
      <h1 className="oc-page-title">
        {mode === "login" ? "Logga in" : "Skapa konto"}
      </h1>
      <p className="oc-page-sub">
        {configured
          ? "Spara lista och historik i molnet."
          : "Supabase är inte konfigurerat — fortsätt som gäst."}
      </p>

      {configured ? (
        <form className="oc-stack" onSubmit={onSubmit} style={{ maxWidth: 360 }}>
          <input
            className="oc-input"
            type="email"
            autoComplete="email"
            placeholder="E-post"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <input
            className="oc-input"
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            placeholder="Lösenord"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
          />
          {mode === "signup" ? (
            <label className="oc-check-row oc-inline">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />
              <span>Jag har läst och accepterar integritetspolicyn</span>
            </label>
          ) : null}
          <button type="submit" className="oc-cta" disabled={busy}>
            {mode === "login" ? "Logga in" : "Skapa konto"}
          </button>
          <button
            type="button"
            className="oc-btn oc-btn-ghost"
            disabled={busy}
            onClick={() => setMode(mode === "login" ? "signup" : "login")}
          >
            {mode === "login" ? "Skapa konto" : "Har konto? Logga in"}
          </button>
        </form>
      ) : null}

      <div className="oc-stack" style={{ maxWidth: 360, marginTop: 16 }}>
        <button type="button" className="oc-cta" onClick={continueGuest}>
          Fortsätt som gäst
        </button>
      </div>

      {msg ? <p className="oc-ok">{msg}</p> : null}
      {error ? <p className="oc-error">{error}</p> : null}
    </section>
  );
}
