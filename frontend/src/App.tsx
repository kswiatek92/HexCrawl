import { NavLink, Outlet } from "react-router-dom";
import { useAuthListener } from "./auth/useAuthListener";
import { useAuthStore } from "./auth/authStore";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  isActive
    ? "font-semibold text-emerald-400"
    : "text-slate-300 hover:text-white";

export default function App() {
  // The one mount point for the Supabase auth subscription (5.12): App wraps
  // every route, so the session is live app-wide before any screen reads it.
  useAuthListener();
  const authStatus = useAuthStore((s) => s.status);

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
          {authStatus === "signed_in" ? "Account" : "Login"}
        </NavLink>
      </nav>
      <main className="px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
