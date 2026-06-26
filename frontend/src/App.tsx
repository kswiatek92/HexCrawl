import { NavLink, Outlet } from "react-router-dom";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  isActive
    ? "font-semibold text-emerald-400"
    : "text-slate-300 hover:text-white";

export default function App() {
  return (
    <div className="min-h-screen bg-slate-900 text-slate-100">
      <nav className="flex gap-4 border-b border-slate-700 px-6 py-4">
        <NavLink to="/" className={linkClass} end>
          Game
        </NavLink>
        <NavLink to="/leaderboard" className={linkClass}>
          Leaderboard
        </NavLink>
        <NavLink to="/login" className={linkClass}>
          Login
        </NavLink>
      </nav>
      <main className="px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
