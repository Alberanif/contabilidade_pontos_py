import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./useAuth";

export const LOGIN_PATH = "/login";
export const TROCAR_SENHA_PATH = "/trocar-senha";

/**
 * Rota-layout que exige sessão. Sem sessão -> /login (guardando a página
 * pedida em `state.from`); com troca de senha pendente -> /trocar-senha.
 * `requireAdmin` restringe a administradores (não-admin volta para "/").
 * Uso: <Route element={<ProtectedRoute />}> ... </Route>
 */
export default function ProtectedRoute({
  requireAdmin = false,
}: {
  requireAdmin?: boolean;
}) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <p className="p-6 text-sm text-gray-500">Carregando...</p>;
  }
  if (!user) {
    return <Navigate to={LOGIN_PATH} replace state={{ from: location }} />;
  }
  if (user.deve_trocar_senha && location.pathname !== TROCAR_SENHA_PATH) {
    return <Navigate to={TROCAR_SENHA_PATH} replace />;
  }
  if (requireAdmin && !user.is_admin) {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}
