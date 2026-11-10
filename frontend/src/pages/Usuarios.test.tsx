import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Usuarios from "./Usuarios";
import {
  listarUsuarios,
  criarUsuario,
  atualizarUsuario,
  redefinirSenha,
  type Usuario,
} from "../api/client";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    listarUsuarios: vi.fn(),
    criarUsuario: vi.fn(),
    atualizarUsuario: vi.fn(),
    redefinirSenha: vi.fn(),
  };
});

function build(overrides: Partial<Usuario> = {}): Usuario {
  return {
    id: 1,
    email: "ana@igt.com",
    nome: "Ana Admin",
    is_admin: true,
    ativo: true,
    deve_trocar_senha: false,
    ultimo_login_em: "2026-03-05T14:30:00",
    criado_em: "2026-01-01T00:00:00",
    ...overrides,
  };
}

const ana = build();
const bruno = build({
  id: 2,
  email: "bruno@igt.com",
  nome: "Bruno Silva",
  is_admin: false,
  ultimo_login_em: null,
});
const carla = build({ id: 3, email: "carla@igt.com", nome: "Carla Souza", is_admin: false, ativo: false });

function erro409(msg: string) {
  return Object.assign(new Error(msg), { status: 409 });
}

describe("Usuarios", () => {
  beforeEach(() => {
    vi.mocked(listarUsuarios).mockReset().mockResolvedValue([ana, bruno, carla]);
    vi.mocked(criarUsuario).mockReset();
    vi.mocked(atualizarUsuario).mockReset();
    vi.mocked(redefinirSenha).mockReset();
  });

  it("lista usuarios com papel, status e ultimo acesso em pt-BR", async () => {
    render(<Usuarios />);
    const linhaAna = await screen.findByTestId("usuario-row-1");
    expect(within(linhaAna).getByText("Ana Admin")).toBeInTheDocument();
    expect(within(linhaAna).getByText("ana@igt.com")).toBeInTheDocument();
    expect(within(linhaAna).getByText("Admin")).toBeInTheDocument();
    expect(within(linhaAna).getByText("Ativo")).toBeInTheDocument();
    expect(within(linhaAna).getByText(/05\/03\/2026/)).toBeInTheDocument();
    const linhaBruno = screen.getByTestId("usuario-row-2");
    expect(within(linhaBruno).getByText("Usuário")).toBeInTheDocument();
    expect(within(linhaBruno).getByText("Nunca acessou")).toBeInTheDocument();
    expect(within(screen.getByTestId("usuario-row-3")).getByText("Desativado")).toBeInTheDocument();
  });

  it("cria usuario e recarrega a lista", async () => {
    vi.mocked(criarUsuario).mockResolvedValue(build({ id: 4 }));
    const user = userEvent.setup();
    render(<Usuarios />);
    await screen.findByTestId("usuario-row-1");
    await user.click(screen.getByRole("button", { name: "+ Novo usuário" }));
    await user.type(screen.getByLabelText("Nome"), "Davi Lima");
    await user.type(screen.getByLabelText("E-mail"), "davi@igt.com");
    await user.type(screen.getByLabelText("Senha provisória"), "Provisoria1");
    await user.selectOptions(screen.getByLabelText("Administrador"), "sim");
    await user.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() =>
      expect(criarUsuario).toHaveBeenCalledWith({
        nome: "Davi Lima",
        email: "davi@igt.com",
        senha_provisoria: "Provisoria1",
        is_admin: true,
      })
    );
    await waitFor(() => expect(listarUsuarios).toHaveBeenCalledTimes(2));
    expect(screen.queryByTestId("usuario-form-overlay")).not.toBeInTheDocument();
  });

  it("mostra erro 409 de e-mail duplicado no formulario e mantem aberto", async () => {
    vi.mocked(criarUsuario).mockRejectedValue(erro409("Email ja cadastrado"));
    const user = userEvent.setup();
    render(<Usuarios />);
    await screen.findByTestId("usuario-row-1");
    await user.click(screen.getByRole("button", { name: "+ Novo usuário" }));
    await user.type(screen.getByLabelText("Nome"), "X");
    await user.type(screen.getByLabelText("E-mail"), "ana@igt.com");
    await user.type(screen.getByLabelText("Senha provisória"), "Provisoria1");
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/e-mail já está em uso/i);
    expect(screen.getByTestId("usuario-form-overlay")).toBeInTheDocument();
  });

  it("edita nome, e-mail e papel", async () => {
    vi.mocked(atualizarUsuario).mockResolvedValue(bruno);
    const user = userEvent.setup();
    render(<Usuarios />);
    const linha = await screen.findByTestId("usuario-row-2");
    await user.click(within(linha).getByRole("button", { name: "Editar" }));
    const nome = screen.getByLabelText("Nome");
    expect(nome).toHaveValue("Bruno Silva");
    expect(screen.queryByLabelText("Senha provisória")).not.toBeInTheDocument();
    await user.clear(nome);
    await user.type(nome, "Bruno S.");
    await user.selectOptions(screen.getByLabelText("Administrador"), "sim");
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() =>
      expect(atualizarUsuario).toHaveBeenCalledWith(2, {
        nome: "Bruno S.",
        email: "bruno@igt.com",
        is_admin: true,
      })
    );
  });

  it("desativa somente apos confirmacao", async () => {
    vi.mocked(atualizarUsuario).mockResolvedValue({ ...bruno, ativo: false });
    const user = userEvent.setup();
    render(<Usuarios />);
    const linha = await screen.findByTestId("usuario-row-2");
    await user.click(within(linha).getByRole("button", { name: "Desativar" }));
    expect(atualizarUsuario).not.toHaveBeenCalled();
    expect(screen.getByText(/Desativar Bruno Silva\?/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirmar" }));
    await waitFor(() => expect(atualizarUsuario).toHaveBeenCalledWith(2, { ativo: false }));
  });

  it("cancelar a confirmacao nao chama a API", async () => {
    const user = userEvent.setup();
    render(<Usuarios />);
    const linha = await screen.findByTestId("usuario-row-2");
    await user.click(within(linha).getByRole("button", { name: "Desativar" }));
    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(atualizarUsuario).not.toHaveBeenCalled();
  });

  it("mostra erro 409 de regra de admin ao desativar", async () => {
    vi.mocked(atualizarUsuario).mockRejectedValue(erro409("Nao e possivel desativar a si mesmo"));
    const user = userEvent.setup();
    render(<Usuarios />);
    const linha = await screen.findByTestId("usuario-row-1");
    await user.click(within(linha).getByRole("button", { name: "Desativar" }));
    await user.click(screen.getByRole("button", { name: "Confirmar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/desativar a si mesmo/i);
  });

  it("reativa sem confirmacao", async () => {
    vi.mocked(atualizarUsuario).mockResolvedValue({ ...carla, ativo: true });
    const user = userEvent.setup();
    render(<Usuarios />);
    const linha = await screen.findByTestId("usuario-row-3");
    await user.click(within(linha).getByRole("button", { name: "Reativar" }));
    await waitFor(() => expect(atualizarUsuario).toHaveBeenCalledWith(3, { ativo: true }));
  });

  it("redefine senha com confirmacao", async () => {
    vi.mocked(redefinirSenha).mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<Usuarios />);
    const linha = await screen.findByTestId("usuario-row-2");
    await user.click(within(linha).getByRole("button", { name: "Redefinir senha" }));
    await user.type(screen.getByLabelText("Nova senha provisória"), "NovaSenha9");
    await user.click(screen.getByRole("button", { name: "Continuar" }));
    expect(redefinirSenha).not.toHaveBeenCalled();
    expect(screen.getByText(/Redefinir a senha de Bruno Silva\?/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirmar" }));
    await waitFor(() => expect(redefinirSenha).toHaveBeenCalledWith(2, "NovaSenha9"));
  });
});
