import { useState, type FormEvent } from "react";

// Os 8 clãs válidos (RF da PRD #28) são um domínio fixo e pequeno — não há
// endpoint de "listar clãs" (ver comentário em CoachesPorCla.tsx), então
// aqui, ao contrário da listagem, faz sentido só hardcodar as 8 opções.
// Não exportadas (mesmo padrão de SubmissionDetail.tsx/ExecutionResult.tsx):
// um arquivo de componente só pode exportar componentes, sob pena de quebrar
// o fast-refresh do eslint.
const CLAN_OPTIONS = [
  "CLÃ 1",
  "CLÃ 2",
  "CLÃ 3",
  "CLÃ 4",
  "CLÃ 5",
  "CLÃ 6",
  "CLÃ 7",
  "CLÃ 8",
];

// As 6 categorias fixas aceitas pelo backend (Literal em
// backend/routers/coach_clas.py `CoachClaCreate`/`CoachClaUpdate`) — mesma
// lista, mesma ordem.
const CATEGORIA_OPTIONS = [
  "Coach",
  "Coach Action",
  "Coach Pro",
  "Coach Hero",
  "Sem Categoria",
  "Novos ULTIMATES",
];

export interface CoachClaFormValues {
  coach: string;
  clan: string;
  categoria: string;
}

interface CoachClaFormProps {
  initialValues?: CoachClaFormValues;
  onSubmit: (values: CoachClaFormValues) => Promise<void>;
  onCancel: () => void;
}

/**
 * Formulário de adicionar/mover/editar um vínculo coach -> clã (issue #7).
 * Um único componente cobre as duas ações da issue:
 * - "Adicionar coach": sem `initialValues`, nome do coach livre.
 * - "Editar" (mover de clã e/ou trocar categoria): `initialValues` presente
 *   e o nome do coach fica travado — `updateCoachCla` só aceita mudar
 *   `clan`/`categoria`, nunca o nome do coach.
 *
 * Erros do `onSubmit` (rede, 422, ou a mensagem de conflito 409 já formatada
 * pelo chamador) são exibidos aqui mesmo, mantendo o formulário aberto para o
 * usuário corrigir e tentar de novo.
 */
export default function CoachClaForm({ initialValues, onSubmit, onCancel }: CoachClaFormProps) {
  const isEdit = initialValues !== undefined;
  const [coach, setCoach] = useState(initialValues?.coach ?? "");
  const [clan, setClan] = useState(initialValues?.clan ?? CLAN_OPTIONS[0]);
  const [categoria, setCategoria] = useState(initialValues?.categoria ?? CATEGORIA_OPTIONS[0]);
  const [submitting, setSubmitting] = useState(false);
  const [erro, setErro] = useState("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const nomeCoach = isEdit ? initialValues!.coach : coach.trim();
    if (!nomeCoach) {
      setErro("Informe o nome do coach.");
      return;
    }
    setErro("");
    setSubmitting(true);
    try {
      await onSubmit({ coach: nomeCoach, clan, categoria });
      // Sucesso: quem chamou é responsável por fechar/desmontar este
      // formulário (ex.: fechando o modal) — não mexemos mais em estado
      // local aqui para evitar "setState em componente desmontado".
    } catch (err) {
      setSubmitting(false);
      setErro(err instanceof Error ? err.message : "Erro ao salvar.");
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label htmlFor="coach-cla-nome" className="block text-xs font-medium text-gray-500 mb-1">
          Nome do coach
        </label>
        <input
          id="coach-cla-nome"
          type="text"
          value={coach}
          onChange={(e) => setCoach(e.target.value)}
          disabled={isEdit}
          className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-full disabled:bg-gray-100 disabled:text-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>

      <div>
        <label htmlFor="coach-cla-clan" className="block text-xs font-medium text-gray-500 mb-1">
          Clã
        </label>
        <select
          id="coach-cla-clan"
          value={clan}
          onChange={(e) => setClan(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          {CLAN_OPTIONS.map((opcao) => (
            <option key={opcao} value={opcao}>
              {opcao}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="coach-cla-categoria" className="block text-xs font-medium text-gray-500 mb-1">
          Categoria
        </label>
        <select
          id="coach-cla-categoria"
          value={categoria}
          onChange={(e) => setCategoria(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          {CATEGORIA_OPTIONS.map((opcao) => (
            <option key={opcao} value={opcao}>
              {opcao}
            </option>
          ))}
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
