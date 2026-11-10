import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { trocarSenha } from "../api/client";
import { useAuth } from "../auth/useAuth";

const MIN_SENHA = 10;

export default function TrocarSenha() {
  const { user, refresh } = useAuth();
  const navigate = useNavigate();
  const obrigatoria = !!user?.deve_trocar_senha;

  const [senhaAtual, setSenhaAtual] = useState("");
  const [novaSenha, setNovaSenha] = useState("");
  const [confirmacao, setConfirmacao] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setErro(null);
    if (novaSenha.length < MIN_SENHA) {
      setErro(`A nova senha deve ter pelo menos ${MIN_SENHA} caracteres.`);
      return;
    }
    if (novaSenha !== confirmacao) {
      setErro("A nova senha e a confirmação não conferem.");
      return;
    }
    setEnviando(true);
    try {
      await trocarSenha(senhaAtual, novaSenha);
      await refresh();
      navigate("/", { replace: true });
    } catch (err) {
      setErro(
        err instanceof Error && err.message
          ? err.message
          : "Não foi possível trocar a senha."
      );
    } finally {
      setEnviando(false);
    }
  }

  const inputClass = "w-full border border-gray-300 rounded px-3 py-2 text-sm";
  const labelClass = "block text-sm font-medium text-gray-700 mb-1";

  return (
    <form
      onSubmit={handleSubmit}
      className="w-full max-w-sm bg-white rounded-lg shadow p-6 space-y-4"
    >
      <h2 className="text-xl font-bold">Trocar senha</h2>
      {obrigatoria && (
        <p className="text-sm text-amber-700">
          A troca de senha é obrigatória antes de continuar.
        </p>
      )}
      <div>
        <label htmlFor="senha-atual" className={labelClass}>Senha atual</label>
        <input
          id="senha-atual"
          type="password"
          autoComplete="current-password"
          required
          value={senhaAtual}
          onChange={(e) => setSenhaAtual(e.target.value)}
          className={inputClass}
        />
      </div>
      <div>
        <label htmlFor="nova-senha" className={labelClass}>Nova senha</label>
        <input
          id="nova-senha"
          type="password"
          autoComplete="new-password"
          required
          value={novaSenha}
          onChange={(e) => setNovaSenha(e.target.value)}
          className={inputClass}
        />
        <p className="text-xs text-gray-500 mt-1">Mínimo de {MIN_SENHA} caracteres.</p>
      </div>
      <div>
        <label htmlFor="confirmar-senha" className={labelClass}>Confirmar nova senha</label>
        <input
          id="confirmar-senha"
          type="password"
          autoComplete="new-password"
          required
          value={confirmacao}
          onChange={(e) => setConfirmacao(e.target.value)}
          className={inputClass}
        />
      </div>
      {erro && (
        <p role="alert" className="text-sm text-red-600">
          {erro}
        </p>
      )}
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={enviando}
          className="bg-indigo-700 text-white rounded px-4 py-2 text-sm font-medium hover:bg-indigo-800 disabled:opacity-50"
        >
          {enviando ? "Salvando..." : "Trocar senha"}
        </button>
        {user && !obrigatoria && (
          <Link to="/" className="text-sm text-gray-600 hover:underline">
            Cancelar
          </Link>
        )}
      </div>
    </form>
  );
}
