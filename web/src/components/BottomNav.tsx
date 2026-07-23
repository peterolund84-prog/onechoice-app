import { NavLink } from "react-router-dom";
import { Clock, Home, List, User } from "lucide-react";

const items: {
  to: string;
  label: string;
  icon: typeof Home;
  end?: boolean;
}[] = [
  { to: "/", label: "Hem", icon: Home, end: true },
  { to: "/lista", label: "Lista", icon: List },
  { to: "/historik", label: "Historik", icon: Clock },
  { to: "/profil", label: "Profil", icon: User },
];

export function BottomNav() {
  return (
    <nav className="oc-nav" aria-label="Huvudnavigering">
      {items.map(({ to, label, icon: Icon, end }) => (
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
              <Icon
                className="oc-nav-icon"
                strokeWidth={isActive ? 2 : 1.5}
                fill="none"
                aria-hidden
              />
              <span>{label}</span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}
