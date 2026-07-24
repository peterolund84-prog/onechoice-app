import { useEffect, useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { api } from "../lib/api";

type NavItem = {
  to: string;
  label: string;
  end?: boolean;
  icon: (active: boolean) => ReactNode;
  badge?: number;
};

function IconHome({ active }: { active: boolean }) {
  if (active) {
    return (
      <svg className="oc-nav-icon" viewBox="0 0 24 24" aria-hidden>
        <path
          fill="currentColor"
          stroke="currentColor"
          strokeWidth="1.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M4 11.5 12 5l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1z"
        />
      </svg>
    );
  }
  return (
    <svg
      className="oc-nav-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M4 11.5 12 5l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1z" />
    </svg>
  );
}

function IconList() {
  return (
    <svg
      className="oc-nav-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01" />
    </svg>
  );
}

function IconClock() {
  return (
    <svg
      className="oc-nav-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v5l3 2" />
    </svg>
  );
}

function IconUser() {
  return (
    <svg
      className="oc-nav-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <circle cx="12" cy="8" r="4" />
      <path d="M5 20a7 7 0 0 1 14 0" />
    </svg>
  );
}

export function BottomNav() {
  const [unchecked, setUnchecked] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      api
        .listShopping()
        .then((data) => {
          if (cancelled) return;
          setUnchecked(data.items.filter((i) => !i.checked).length);
        })
        .catch(() => {
          /* ignore */
        });
    };
    load();
    const t = window.setInterval(load, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, []);

  const items: NavItem[] = [
    {
      to: "/",
      label: "Hem",
      end: true,
      icon: (active) => <IconHome active={active} />,
    },
    {
      to: "/lista",
      label: "Lista",
      icon: () => <IconList />,
      badge: unchecked,
    },
    { to: "/historik", label: "Historik", icon: () => <IconClock /> },
    { to: "/profil", label: "Profil", icon: () => <IconUser /> },
  ];

  return (
    <nav className="oc-nav" aria-label="Huvudnavigering">
      {items.map(({ to, label, icon, end, badge }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            isActive ? "oc-nav-item is-active" : "oc-nav-item"
          }
        >
          {({ isActive }) => (
            <>
              <span className="oc-nav-icon-wrap">
                {icon(isActive)}
                {badge && badge > 0 ? (
                  <span className="oc-nav-badge">{badge > 99 ? "99+" : badge}</span>
                ) : null}
              </span>
              <span>{label}</span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}
