import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";

const links = [
  { to: "/", label: "Dashboard" },
  { to: "/registros", label: "Registros" },
  { to: "/desafios", label: "Desafios" },
  { to: "/contabilidade", label: "Contabilidade" },
  { to: "/coaches-por-cla", label: "Coaches por Clã" },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const visibleLinks = user?.is_admin
    ? [...links, { to: "/usuarios", label: "Usuários" }]
    : links;

  async function handleSair() {
    await logout().catch(() => {});
    navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-indigo-700 text-white shadow-lg">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-8">
          <h1 className="text-lg font-bold tracking-tight">
            IGT ULTIMATE - Pontos
          </h1>
          <div className="flex gap-1">
            {visibleLinks.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-white/20"
                      : "hover:bg-white/10"
                  }`
                }
              >
                {link.label}
              </NavLink>
            ))}
          </div>
          {user && (
            <div className="ml-auto flex items-center gap-3 text-sm">
              <span>{user.nome}</span>
              <button
                type="button"
                onClick={handleSair}
                className="px-3 py-1.5 rounded font-medium hover:bg-white/10 transition-colors"
              >
                Sair
              </button>
            </div>
          )}
        </div>
      </nav>
      <main className="max-w-7xl mx-auto px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
