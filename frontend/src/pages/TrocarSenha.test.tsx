import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "../auth/AuthContext";
import TrocarSenha from "./TrocarSenha";
import { fetchMe, trocarSenha, type Usuario } from "../api/client";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, fetchMe: vi.fn(), trocarSenha: vi.fn() };
});

function buildUsuario(overrides: Partial<Usuario> = {}): Usuario {
  return {
    id: 1,
    email: "ana@igt.com",
    nome: "Ana",
    is_admin: false,
    ativo: true,
    deve_trocar_senha: false,
    ultimo_login_em: null,
    criado_em: "2026-01-01T00:00:00",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/trocar-senha"]}>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<p>Pagina inicial</p>} />
          <Route path="/trocar-senha" element={<TrocarSenha />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );
}

async function preencher(atual: string, nova: string, conf: string) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Senha atual"), atual);
  await user.type(screen.getByLabelText("Nova senha"), nova);
  await user.type(screen.getByLabelText("Confirmar nova senha"), conf);
  await user.click(screen.getByRole("button", { name: "Trocar senha" }));
}

describe("TrocarSenha", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(fetchMe).mockResolvedValue(buildUsuario());
  });

  it("rejeita nova senha com menos de 10 caracteres", async () => {
    renderPage();
    await preencher("antiga", "curta123", "curta123");
    expect(await screen.findByRole("alert")).toHaveTextContent(/10 caracteres/);
    expect(trocarSenha).not.toHaveBeenCalled();
  });

  it("rejeita confirmacao diferente", async () => {
    renderPage();
    await preencher("antiga", "senhanova123", "senhanova124");
    expect(await screen.findByRole("alert")).toHaveTextContent(/não conferem/);
    expect(trocarSenha).not.toHaveBeenCalled();
  });

  it("exibe o erro do servidor", async () => {
    vi.mocked(trocarSenha).mockRejectedValue(new Error("Senha atual incorreta"));
    renderPage();
    await preencher("errada", "senhanova123", "senhanova123");
    expect(await screen.findByRole("alert")).toHaveTextContent("Senha atual incorreta");
  });

  it("troca, atualiza o usuario e vai para o dashboard", async () => {
    vi.mocked(trocarSenha).mockResolvedValue(undefined);
    renderPage();
    await preencher("antiga", "senhanova123", "senhanova123");
    expect(await screen.findByText("Pagina inicial")).toBeInTheDocument();
    expect(trocarSenha).toHaveBeenCalledWith("antiga", "senhanova123");
    expect(fetchMe).toHaveBeenCalledTimes(2);
  });

  it("troca voluntaria mostra link para cancelar", async () => {
    renderPage();
    expect(await screen.findByRole("link", { name: "Cancelar" })).toHaveAttribute("href", "/");
  });

  it("troca obrigatoria nao mostra cancelar", async () => {
    vi.mocked(fetchMe).mockResolvedValue(buildUsuario({ deve_trocar_senha: true }));
    renderPage();
    await screen.findByLabelText("Senha atual");
    await waitFor(() => expect(screen.getByText(/obrigatória/i)).toBeInTheDocument());
    expect(screen.queryByRole("link", { name: "Cancelar" })).toBeNull();
  });
});
