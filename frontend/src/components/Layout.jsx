import { NavLink, Outlet } from "react-router-dom";

const NAV_LINKS = [
  { to: "/", label: "Overview", end: true },
  { to: "/forecast", label: "Forecast" },
  { to: "/recommend", label: "Recommendation" },
];

export default function Layout() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-title">
          <span className="app-header-name">Freight Charter Compass</span>
          <span className="app-header-sub">SIH26006 — Ministry of Steel</span>
        </div>
        <nav className="app-nav">
          {NAV_LINKS.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={({ isActive }) =>
                isActive ? "app-nav-link app-nav-link-active" : "app-nav-link"
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
      <footer className="app-footer">
        Every figure on this site is labelled REAL, CALCULATED, SIMULATED,
        or ASSUMPTION — see each page's sourcing notes.
      </footer>
    </div>
  );
}
