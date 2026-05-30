import { NavLink } from "react-router-dom";

const links = [
  { to: "/", label: "仪表盘", end: true },
  { to: "/records", label: "记录" },
  { to: "/plugins", label: "插件" },
  { to: "/config", label: "配置" },
];

export default function Nav() {
  return (
    <header>
      <div className="brand">🎬 MediaMaid</div>
      <nav>
        {links.map((l) => (
          <NavLink
            key={l.to}
            to={l.to}
            end={l.end}
            className={({ isActive }) => (isActive ? "on" : "")}
          >
            {l.label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}
