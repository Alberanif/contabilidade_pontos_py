import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  listarUsuarios,
  criarUsuario,
  atualizarUsuario,
  redefinirSenha,
  type Usuario,
} from "../api/client";
import UsuarioForm, { type UsuarioFormValues } from "../components/UsuarioForm";

type ModalState =
  | { kind: "criar" }
  | { kind: "editar"; usuario: Usuario }
  | { kind: "desativar"; usuario: Usuario }
  | { kind: "senha"; usuario: Usuario; senha: string; confirmando: boolean }
  | null;

/** Traduz erros da API (409 em especial) para mensagens legíveis. */
function mensagemErro(err: unknown): string {
  if (!(err instanceof Error)) return "Erro inesperado.";
  const status = (err as Error & { status?: number }).status;
  if (status === 409 && /e-?mail/i.test(err.message)) {
    return "Este e-mail já está em uso por outro usuário.";
  }
  if (status === 409) return `Operação não permitida: ${err.message}`;
  return err.message;
}

function formatarUltimoAcesso(valor: string | null): string {
  if (!valor) return "Nunca acessou";
  const data = new Date(valor);
  if (Number.isNaN(data.getTime())) return valor;
  return data.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

const BTN_LINK = "text-xs font-medium text-indigo-600 hover:text-indigo-800 disabled:opacity-50";

export default function Usuarios() {
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState("");
  const [modal, setModal] = useState<ModalState>(null);
  const [busy, setBusy] = useState(false);

  const carregar = useCallback(async () => {
    try {
      setUsuarios(await listarUsuarios());
      setErro("");
    } catch (err) {
      setErro(mensagemErro(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function handleSalvar(values: UsuarioFormValues) {
    if (modal?.kind === "criar") {
      await criarUsuario({
        nome: values.nome,
        email: values.email,
        senha_provisoria: values.senha_provisoria ?? "",
        is_admin: values.is_admin,
      });
    } else if (modal?.kind === "editar") {
      await atualizarUsuario(modal.usuario.id, {
        nome: values.nome,
        email: values.email,
        is_admin: values.is_admin,
      });
    }
    setModal(null);
    await carregar();
  }

  async function mudarAtivo(usuario: Usuario, ativo: boolean) {
    setBusy(true);
    setErro("");
    try {
      await atualizarUsuario(usuario.id, { ativo });
      setModal(null);
      await carregar();
    } catch (err) {
      setModal(null);
      setErro(mensagemErro(err));
    } finally {
      setBusy(false);
    }
  }

  async function executarRedefinicao(usuario: Usuario, senha: string) {
    setBusy(true);
    setErro("");
    try {
      await redefinirSenha(usuario.id, senha);
      setModal(null);
      await carregar();
    } catch (err) {
      setModal(null);
      setErro(mensagemErro(err));
    } finally {
      setBusy(false);
    }
  }

  function handleContinuarSenha(e: FormEvent) {
    e.preventDefault();
    if (modal?.kind !== "senha" || !modal.senha) return;
    setModal({ ...modal, confirmando: true });
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <h2 className="text-2xl font-bold text-gray-800">Usuários</h2>
        <button
          onClick={() => setModal({ kind: "criar" })}
          className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-3 py-1.5 rounded-lg shadow-sm transition-colors"
        >
          + Novo usuário
        </button>
      </div>

      {erro && (
        <div role="alert" className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {erro}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-gray-500">Carregando...</p>
      ) : (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs font-medium text-gray-400 uppercase tracking-wide">
                <th className="px-5 py-2 font-medium">Nome</th>
                <th className="px-5 py-2 font-medium">E-mail</th>
                <th className="px-5 py-2 font-medium">Papel</th>
                <th className="px-5 py-2 font-medium">Status</th>
                <th className="px-5 py-2 font-medium">Último acesso</th>
                <th className="px-5 py-2 font-medium text-right">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {usuarios.map((u) => (
                <tr key={u.id} data-testid={`usuario-row-${u.id}`} className="hover:bg-gray-50 transition-colors">
                  <td className="px-5 py-2.5 font-medium text-gray-800 whitespace-nowrap">{u.nome}</td>
                  <td className="px-5 py-2.5 text-gray-600">{u.email}</td>
                  <td className="px-5 py-2.5">{u.is_admin ? "Admin" : "Usuário"}</td>
                  <td className="px-5 py-2.5">
                    <span
                      className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                        u.ativo ? "bg-green-100 text-green-700" : "bg-gray-200 text-gray-600"
                      }`}
                    >
                      {u.ativo ? "Ativo" : "Desativado"}
                    </span>
                  </td>
                  <td className="px-5 py-2.5 text-gray-600 whitespace-nowrap">
                    {formatarUltimoAcesso(u.ultimo_login_em)}
                  </td>
                  <td className="px-5 py-2.5 text-right whitespace-nowrap space-x-3">
                    <button className={BTN_LINK} onClick={() => setModal({ kind: "editar", usuario: u })}>
                      Editar
                    </button>
                    <button
                      className={BTN_LINK}
                      onClick={() => setModal({ kind: "senha", usuario: u, senha: "", confirmando: false })}
                    >
                      Redefinir senha
                    </button>
                    {u.ativo ? (
                      <button
                        className="text-xs font-medium text-red-600 hover:text-red-800"
                        onClick={() => setModal({ kind: "desativar", usuario: u })}
                      >
                        Desativar
                      </button>
                    ) : (
                      <button className={BTN_LINK} disabled={busy} onClick={() => void mudarAtivo(u, true)}>
                        Reativar
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modal && (
        <div
          data-testid="usuario-form-overlay"
          className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50"
        >
          <div className="bg-white rounded-xl shadow-lg p-6 w-full max-w-md">
            {(modal.kind === "criar" || modal.kind === "editar") && (
              <>
                <h3 className="text-lg font-bold text-gray-800 mb-4">
                  {modal.kind === "criar" ? "Novo usuário" : `Editar ${modal.usuario.nome}`}
                </h3>
                <UsuarioForm
                  usuario={modal.kind === "editar" ? modal.usuario : undefined}
                  onSubmit={async (values) => {
                    try {
                      await handleSalvar(values);
                    } catch (err) {
                      throw new Error(mensagemErro(err));
                    }
                  }}
                  onCancel={() => setModal(null)}
                />
              </>
            )}

            {modal.kind === "desativar" && (
              <>
                <h3 className="text-lg font-bold text-gray-800 mb-2">Desativar {modal.usuario.nome}?</h3>
                <p className="text-sm text-gray-600 mb-4">
                  O usuário não conseguirá mais entrar no sistema. Você pode reativá-lo depois.
                </p>
                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => setModal(null)}
                    className="text-sm font-medium text-gray-600 hover:text-gray-800 px-3 py-1.5 rounded-lg"
                  >
                    Cancelar
                  </button>
                  <button
                    disabled={busy}
                    onClick={() => void mudarAtivo(modal.usuario, false)}
                    className="bg-red-600 hover:bg-red-700 text-white text-sm font-medium px-4 py-1.5 rounded-lg shadow-sm disabled:opacity-50"
                  >
                    Confirmar
                  </button>
                </div>
              </>
            )}

            {modal.kind === "senha" && !modal.confirmando && (
              <form onSubmit={handleContinuarSenha}>
                <h3 className="text-lg font-bold text-gray-800 mb-4">Redefinir senha de {modal.usuario.nome}</h3>
                <label htmlFor="usuario-nova-senha" className="block text-xs font-medium text-gray-500 mb-1">
                  Nova senha provisória
                </label>
                <input
                  id="usuario-nova-senha"
                  type="password"
                  autoComplete="new-password"
                  value={modal.senha}
                  onChange={(e) => setModal({ ...modal, senha: e.target.value })}
                  className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
                <div className="flex justify-end gap-2 pt-4">
                  <button
                    type="button"
                    onClick={() => setModal(null)}
                    className="text-sm font-medium text-gray-600 hover:text-gray-800 px-3 py-1.5 rounded-lg"
                  >
                    Cancelar
                  </button>
                  <button
                    type="submit"
                    disabled={!modal.senha}
                    className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-1.5 rounded-lg shadow-sm disabled:opacity-50"
                  >
                    Continuar
                  </button>
                </div>
              </form>
            )}

            {modal.kind === "senha" && modal.confirmando && (
              <>
                <h3 className="text-lg font-bold text-gray-800 mb-2">
                  Redefinir a senha de {modal.usuario.nome}?
                </h3>
                <p className="text-sm text-gray-600 mb-4">
                  A senha atual deixará de funcionar e o usuário deverá trocar a nova senha no próximo acesso.
                </p>
                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => setModal(null)}
                    className="text-sm font-medium text-gray-600 hover:text-gray-800 px-3 py-1.5 rounded-lg"
                  >
                    Cancelar
                  </button>
                  <button
                    disabled={busy}
                    onClick={() => void executarRedefinicao(modal.usuario, modal.senha)}
                    className="bg-red-600 hover:bg-red-700 text-white text-sm font-medium px-4 py-1.5 rounded-lg shadow-sm disabled:opacity-50"
                  >
                    Confirmar
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
