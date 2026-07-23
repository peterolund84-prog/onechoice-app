import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { api } from "../lib/api";
import type { ShoppingItem } from "../lib/types";

const CATEGORY_ORDER = [
  "frukt & grönt",
  "kött & fisk",
  "mejeri",
  "skafferi",
  "fryst",
  "övrigt",
];

export function ListaPage() {
  const [items, setItems] = useState<ShoppingItem[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shareHint, setShareHint] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await api.listShopping();
      setItems(data.items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Kunde inte ladda listan");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const open = useMemo(() => items.filter((i) => !i.checked), [items]);
  const done = useMemo(() => items.filter((i) => i.checked), [items]);

  const grouped = useMemo(() => {
    const map = new Map<string, ShoppingItem[]>();
    for (const item of open) {
      const cat = item.category || "övrigt";
      if (!map.has(cat)) map.set(cat, []);
      map.get(cat)!.push(item);
    }
    return CATEGORY_ORDER.filter((c) => map.has(c)).map((c) => ({
      category: c,
      items: map.get(c)!,
    }));
  }, [open]);

  async function onAdd(e: FormEvent) {
    e.preventDefault();
    const n = name.trim();
    if (!n) return;
    setBusy(true);
    try {
      await api.addShopping(n);
      setName("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kunde inte lägga till");
    } finally {
      setBusy(false);
    }
  }

  async function onToggle(item: ShoppingItem) {
    setItems((prev) =>
      prev.map((x) =>
        x.id === item.id ? { ...x, checked: !x.checked } : x,
      ),
    );
    try {
      await api.toggleShopping(item.id, !item.checked);
    } catch {
      await load();
    }
  }

  async function onClearDone() {
    setBusy(true);
    try {
      await api.clearCheckedShopping(done.map((d) => d.id));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kunde inte rensa");
    } finally {
      setBusy(false);
    }
  }

  async function onShare() {
    try {
      const text = await api.shoppingShareText();
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        setShareHint("Kopierad till urklipp");
      } else {
        setShareHint(text);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kunde inte dela");
    }
  }

  return (
    <section className="oc-page">
      <h1 className="oc-page-title">Lista</h1>
      <p className="oc-page-sub">Inköpslista — gästläge sparar lokalt på API:t.</p>

      <form className="oc-row-form" onSubmit={onAdd}>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Lägg till vara"
          maxLength={120}
          aria-label="Ny vara"
        />
        <button type="submit" className="oc-btn" disabled={busy || !name.trim()}>
          Lägg till
        </button>
      </form>

      {open.length === 0 && done.length === 0 ? (
        <p className="oc-empty">Listan är tom. Acceptera ett matbeslut eller lägg till manuellt.</p>
      ) : null}

      {grouped.map((g) => (
        <div key={g.category} className="oc-group">
          <h2 className="oc-group-title">{g.category}</h2>
          <ul className="oc-list">
            {g.items.map((item) => (
              <li key={item.id}>
                <label className="oc-check-row">
                  <input
                    type="checkbox"
                    checked={false}
                    onChange={() => onToggle(item)}
                  />
                  <span>{item.name}</span>
                </label>
              </li>
            ))}
          </ul>
        </div>
      ))}

      {done.length > 0 ? (
        <div className="oc-group">
          <div className="oc-group-head">
            <h2 className="oc-group-title">Klart ({done.length})</h2>
            <button type="button" className="oc-text-btn" disabled={busy} onClick={onClearDone}>
              Rensa klara
            </button>
          </div>
          <ul className="oc-list">
            {done.map((item) => (
              <li key={item.id}>
                <label className="oc-check-row is-done">
                  <input
                    type="checkbox"
                    checked
                    onChange={() => onToggle(item)}
                  />
                  <span>{item.name}</span>
                </label>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {open.length > 0 ? (
        <button type="button" className="oc-btn oc-btn-ghost" onClick={onShare}>
          Dela lista
        </button>
      ) : null}

      {shareHint ? <pre className="oc-share-hint">{shareHint}</pre> : null}
      {error ? <p className="oc-error">{error}</p> : null}
    </section>
  );
}
