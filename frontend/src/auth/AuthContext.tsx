import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  fetchMe,
  login as apiLogin,
  logout as apiLogout,
  setAuthEventHandlers,
  type Usuario,
} from "../api/client";

export interface AuthContextValue {
  /** Usuário da sessão atual; null quando não autenticado. */
  user: Usuario | null;
  /** true enquanto o `GET /api/auth/me` inicial não respondeu. */
  loading: boolean;
  login: (email: string, senha: string) => Promise<Usuario>;
  logout: () => Promise<void>;
  /** Recarrega o usuário (ex.: após trocar a senha, limpa `deve_trocar_senha`). */
  refresh: () => Promise<Usuario | null>;
}

// eslint-disable-next-line react-refresh/only-export-components
export const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Usuario | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const me = await fetchMe();
      setUser(me);
      return me;
    } catch {
      setUser(null);
      return null;
    }
  }, []);

  useEffect(() => {
    setAuthEventHandlers({
      onUnauthorized: () => setUser(null),
      onPasswordChangeRequired: () =>
        setUser((u) => (u ? { ...u, deve_trocar_senha: true } : u)),
    });
    refresh().finally(() => setLoading(false));
    return () => setAuthEventHandlers({});
  }, [refresh]);

  const login = useCallback(async (email: string, senha: string) => {
    const u = await apiLogin(email, senha);
    setUser(u);
    return u;
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } finally {
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, logout, refresh }),
    [user, loading, login, logout, refresh]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
