import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import { AuthProvider } from "./AuthContext";
import ProtectedRoute from "./ProtectedRoute";
import Login from "../pages/Login";
import Layout from "../components/Layout";
import { fetchMe, login, logout, type Usuario } from "../api/client";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, fetchMe: vi.fn(), login: vi.fn(), logout: vi.fn() };
});

function buildUsuario(overrides: Partial<Usuario> = {}): Usuario {
  return {
    id: 1,
    email: "ana@igt.com",
    nome: "Ana Admin",
    is_admin: false,
    ativo: true,
    deve_trocar_senha: false,
    ultimo_login_em: null,
    criado_em: "2026-01-01T00:00:00",
    ...overrides,
  };
}

function Where() {
  const loc = useLocation();
  return <div data-testid="where">{loc.pathname}</div>;
}

function renderApp(initial: string) {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <AuthProvider>
        <Where />
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<Layout />}>
              <Route path="/" element={<p>Pagina inicial</p>} />
              <Route path="/registros" element={<p>Pagina registros</p>} />
              <Route path="/trocar-senha" element={<p>Pagina troca</p>} />
              <Route element={<ProtectedRoute requireAdmin />}>
                <Route path="/usuarios" element={<p>Pagina usuarios</p>} />
              </Route>
            </Route>
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );
}

function semSessao() {
  vi.mocked(fetchMe).mockRejectedValue(
    Object.assign(new Error("Nao autenticado"), { status: 401 })
  );
}

describe("rotas protegidas", () => {
  beforeEach(() => {
    vi.mocked(fetchMe).mockReset();
    vi.mocked(login).mockReset();
    vi.mocked(logout).mockReset();
  });

  it("sem sessao, redireciona para /login", async () => {
    semSessao();
    renderApp("/registros");
    expect(await screen.findByLabelText("E-mail")).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent("/login");
  });

  it("apos o login volta para a pagina originalmente pedida", async () => {
    semSessao();
    vi.mocked(login).mockResolvedValue(buildUsuario());
    renderApp("/registros");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("E-mail"), "ana@igt.com");
    await user.type(screen.getByLabelText("Senha"), "segredo");
    await user.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByText("Pagina registros")).toBeInTheDocument();
    expect(login).toHaveBeenCalledWith("ana@igt.com", "segredo");
  });

  it("com troca de senha pendente, redireciona para /trocar-senha", async () => {
    vi.mocked(fetchMe).mockResolvedValue(buildUsuario({ deve_trocar_senha: true }));
    renderApp("/registros");
    expect(await screen.findByText("Pagina troca")).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent("/trocar-senha");
  });

  it("nao-admin e barrado em /usuarios", async () => {
    vi.mocked(fetchMe).mockResolvedValue(buildUsuario());
    renderApp("/usuarios");
    expect(await screen.findByText("Pagina inicial")).toBeInTheDocument();
  });

  it("admin acessa /usuarios", async () => {
    vi.mocked(fetchMe).mockResolvedValue(buildUsuario({ is_admin: true }));
    renderApp("/usuarios");
    expect(await screen.findByText("Pagina usuarios")).toBeInTheDocument();
  });
});

describe("login", () => {
  beforeEach(() => {
    vi.mocked(fetchMe).mockReset();
    vi.mocked(login).mockReset();
    semSessao();
  });

  async function preencherEEnviar() {
    renderApp("/login");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("E-mail"), "ana@igt.com");
    await user.type(screen.getByLabelText("Senha"), "errada");
    await user.click(screen.getByRole("button", { name: "Entrar" }));
  }

  it("mostra erro generico em credenciais invalidas (401)", async () => {
    vi.mocked(login).mockRejectedValue(Object.assign(new Error("x"), { status: 401 }));
    await preencherEEnviar();
    expect(await screen.findByRole("alert")).toHaveTextContent("E-mail ou senha inválidos");
  });

  it("mostra mensagem de bloqueio no 429", async () => {
    vi.mocked(login).mockRejectedValue(Object.assign(new Error("x"), { status: 429 }));
    await preencherEEnviar();
    expect(await screen.findByRole("alert")).toHaveTextContent(/bloqueado/i);
  });
});

describe("Layout", () => {
  beforeEach(() => {
    vi.mocked(fetchMe).mockReset();
    vi.mocked(logout).mockReset();
  });

  it("mostra o nome do usuario e oculta 'Usuarios' para nao-admin", async () => {
    vi.mocked(fetchMe).mockResolvedValue(buildUsuario({ nome: "Bia Coach" }));
    renderApp("/");
    expect(await screen.findByText("Bia Coach")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Usuários" })).not.toBeInTheDocument();
  });

  it("mostra o link 'Usuarios' para admin", async () => {
    vi.mocked(fetchMe).mockResolvedValue(buildUsuario({ is_admin: true }));
    renderApp("/");
    expect(await screen.findByRole("link", { name: "Usuários" })).toBeInTheDocument();
  });

  it("Sair encerra a sessao e volta ao login", async () => {
    vi.mocked(fetchMe).mockResolvedValue(buildUsuario());
    vi.mocked(logout).mockResolvedValue(undefined);
    renderApp("/");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Sair" }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/login"));
    expect(logout).toHaveBeenCalled();
  });
});
