import { useState, type FormEvent } from "react";
import type { Usuario } from "../api/client";

export interface UsuarioFormValues {
  nome: string;
  email: string;
  is_admin: boolean;
  /** Presente apenas na criação. */
  senha_provisoria?: string;
}

interface UsuarioFormProps {
  /** Quando presente, o formulário edita este usuário (sem campo de senha). */
  usuario?: Usuario;
  onSubmit: (values: UsuarioFormValues) => Promise<void>;
  onCancel: () => void;
}

const INPUT =
  "border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-500";
const LABEL = "block text-xs font-medium text-gray-500 mb-1";

/** Formulário de criar/editar usuário (issue #62). Erros do `onSubmit` ficam visíveis aqui. */
export default function UsuarioForm({ usuario, onSubmit, onCancel }: UsuarioFormProps) {
  const isEdit = usuario !== undefined;
  const [nome, setNome] = useState(usuario?.nome ?? "");
  const [email, setEmail] = useState(usuario?.email ?? "");
  const [senha, setSenha] = useState("");
  const [admin, setAdmin] = useState<"sim" | "nao">(usuario?.is_admin ? "sim" : "nao");
  const [submitting, setSubmitting] = useState(false);
  const [erro, setErro] = useState("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!nome.trim() || !email.trim() || (!isEdit && !senha)) {
      setErro("Preencha todos os campos obrigatórios.");
      return;
    }
    setErro("");
    setSubmitting(true);
    try {
      const values: UsuarioFormValues = {
        nome: nome.trim(),
        email: email.trim(),
        is_admin: admin === "sim",
      };
      if (!isEdit) values.senha_provisoria = senha;
      await onSubmit(values);
    } catch (err) {
      setSubmitting(false);
      setErro(err instanceof Error ? err.message : "Erro ao salvar.");
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label htmlFor="usuario-nome" className={LABEL}>
          Nome
        </label>
        <input id="usuario-nome" type="text" value={nome} onChange={(e) => setNome(e.target.value)} className={INPUT} />
      </div>
      <div>
        <label htmlFor="usuario-email" className={LABEL}>
          E-mail
        </label>
        <input
          id="usuario-email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className={INPUT}
        />
      </div>
      {!isEdit && (
        <div>
          <label htmlFor="usuario-senha" className={LABEL}>
            Senha provisória
          </label>
          <input
            id="usuario-senha"
            type="password"
            autoComplete="new-password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            className={INPUT}
          />
          <p className="text-xs text-gray-400 mt-1">O usuário deverá trocá-la no primeiro acesso.</p>
        </div>
      )}
      <div>
        <label htmlFor="usuario-admin" className={LABEL}>
          Administrador
        </label>
        <select
          id="usuario-admin"
          value={admin}
          onChange={(e) => setAdmin(e.target.value as "sim" | "nao")}
          className={INPUT}
        >
          <option value="nao">Não</option>
          <option value="sim">Sim</option>
        </select>
      </div>

      {erro && (
        <p className="text-sm text-red-600" role="alert">
          {erro}
        </p>
      )}

      <div className="flex items-center justify-end gap-2 pt-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={submitting}
          className="text-sm font-medium text-gray-600 hover:text-gray-800 px-3 py-1.5 rounded-lg disabled:opacity-50"
        >
          Cancelar
        </button>
        <button
          type="submit"
          disabled={submitting}
          className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-1.5 rounded-lg shadow-sm disabled:opacity-50"
        >
          {submitting ? "Salvando..." : "Salvar"}
        </button>
      </div>
    </form>
  );
}
