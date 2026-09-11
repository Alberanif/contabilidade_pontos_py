import { useEffect, useMemo, useState } from "react";
import {
  fetchCoachClas,
  createCoachCla,
  updateCoachCla,
  deleteCoachCla,
  type CoachCla,
} from "../api/client";
import CoachClaForm, { type CoachClaFormValues } from "../components/CoachClaForm";

// Página "Coaches por Clã" (issue #6, PRD #28), com CRUD adicionado na
// issue #7: adicionar, mover de clã, editar categoria e remover um coach —
// tudo pela UI, sem precisar de SQL ou reimportação de CSV. Continua sem
// nenhuma exibição de pontos/totais (fora de escopo desta tela).

function normalizarBusca(texto: string): string {
  return texto.trim().toLocaleLowerCase("pt-BR");
}

// Agrupa a lista plana retornada pela API em um mapa clã -> coaches,
// preservando a ordem de primeira aparição de cada clã (não há endpoint de
// "listar todos os clãs possíveis", então só mostramos os que aparecem nos
// dados — ver comentário na issue).
function agruparPorClan(coaches: CoachCla[]): Map<string, CoachCla[]> {
  const grupos = new Map<string, CoachCla[]>();
  for (const c of coaches) {
    const lista = grupos.get(c.clan);
    if (lista) {
      lista.push(c);
    } else {
      grupos.set(c.clan, [c]);
    }
  }
  return grupos;
}

// Extrai o clã atual da mensagem 409 do backend
// ("Coach 'X' já pertence ao clã 'CLÃ 1'. Use PUT ... para mover de clã.")
// para montar uma mensagem amigável, sem expor detalhes técnicos de rota
// HTTP ao usuário final.
function extrairClanDoErro409(mensagem: string): string | null {
  const match = mensagem.match(/clã '([^']+)'/i);
  return match ? match[1] : null;
}

type FormState = { mode: "add" } | { mode: "edit"; coach: CoachCla };

export default function CoachesPorCla() {
  const [coaches, setCoaches] = useState<CoachCla[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState("");
  const [busca, setBusca] = useState("");
  const [formState, setFormState] = useState<FormState | null>(null);
  const [confirmandoRemocao, setConfirmandoRemocao] = useState<string | null>(null);

  useEffect(() => {
    let cancelado = false;
    // Sem dependências: roda uma única vez, ao montar — os valores iniciais de
    // `loading`/`erro` já cobrem o estado de carregamento inicial.
    fetchCoachClas()
      .then((data) => {
        if (!cancelado) setCoaches(data);
      })
      .catch((e) => {
        if (!cancelado) setErro(e instanceof Error ? e.message : "Erro ao carregar coaches por clã");
      })
      .finally(() => {
        if (!cancelado) setLoading(false);
      });
    return () => {
      cancelado = true;
    };
  }, []);

  // Revalida a lista a partir do servidor após qualquer operação de
  // CRUD bem-sucedida, para refletir o estado atualizado sem exigir reload
  // manual da página.
  async function recarregarLista() {
    try {
      const data = await fetchCoachClas();
      setCoaches(data);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Erro ao carregar coaches por clã");
    }
  }

  async function handleAdicionar(values: CoachClaFormValues) {
    try {
      await createCoachCla(values);
    } catch (err) {
      const e = err as Error & { status?: number };
      if (e.status === 409) {
        const clanAtual = extrairClanDoErro409(e.message) ?? "outro clã";
        throw new Error(`Este coach já está no ${clanAtual}. Use "Editar" para movê-lo.`);
      }
      throw new Error(e.message || "Erro ao adicionar coach.");
    }
    setFormState(null);
    await recarregarLista();
  }

  async function handleEditar(coachCanonico: string, values: CoachClaFormValues) {
    try {
      await updateCoachCla(coachCanonico, { clan: values.clan, categoria: values.categoria });
    } catch (err) {
      const e = err as Error;
      throw new Error(e.message || "Erro ao atualizar coach.");
    }
    setFormState(null);
    await recarregarLista();
  }

  async function handleRemover(coachCanonico: string) {
    try {
      await deleteCoachCla(coachCanonico);
      setConfirmandoRemocao(null);
      await recarregarLista();
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao remover coach.");
      setConfirmandoRemocao(null);
    }
  }

  const coachesFiltrados = useMemo(() => {
    const termo = normalizarBusca(busca);
    if (!termo) return coaches;
    return coaches.filter((c) => normalizarBusca(c.coach_canonico).includes(termo));
  }, [coaches, busca]);

  const grupos = useMemo(() => agruparPorClan(coachesFiltrados), [coachesFiltrados]);
  // Ordena os clãs alfabeticamente (ex.: "CLÃ 1" ... "CLÃ 8") para uma exibição estável.
  const claOrdenados = useMemo(
    () => Array.from(grupos.keys()).sort((a, b) => a.localeCompare(b, "pt-BR", { numeric: true })),
    [grupos]
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <h2 className="text-2xl font-bold text-gray-800">Coaches por Clã</h2>
        <div className="flex items-end gap-4">
          <div>
            <label htmlFor="busca-coach" className="block text-xs font-medium text-gray-500 mb-1">
              Buscar por nome
            </label>
            <input
              id="busca-coach"
              type="text"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Nome do coach"
              className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-56 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <button
            onClick={() => setFormState({ mode: "add" })}
            className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-3 py-1.5 rounded-lg shadow-sm transition-colors"
          >
            + Adicionar coach
          </button>
        </div>
      </div>

      {erro && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">{erro}</div>
      )}

      {loading ? (
        <p className="text-gray-500">Carregando coaches...</p>
      ) : coaches.length === 0 ? (
        <p className="text-gray-500">Nenhum coach cadastrado ainda.</p>
      ) : claOrdenados.length === 0 ? (
        <p className="text-gray-500">Nenhum coach encontrado para essa busca.</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {claOrdenados.map((clan) => {
            const coachesDoClan = grupos.get(clan) ?? [];
            return (
              <div
                key={clan}
                data-testid={`clan-section-${clan}`}
                className="bg-white rounded-xl shadow-sm border border-gray-200 p-4 space-y-3"
              >
                <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">{clan}</h3>
                <ul className="divide-y divide-gray-100">
                  {coachesDoClan.map((c) => (
                    <li
                      key={c.coach_canonico}
                      data-testid={`coach-row-${c.coach_canonico}`}
                      className="py-2 flex items-center justify-between gap-2 flex-wrap"
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-gray-800">{c.coach_canonico}</span>
                        <span className="px-2 py-0.5 rounded text-xs font-medium bg-indigo-100 text-indigo-700 whitespace-nowrap">
                          {c.categoria}
                        </span>
                      </div>
                      {confirmandoRemocao === c.coach_canonico ? (
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-red-600">Remover este coach?</span>
                          <button
                            onClick={() => handleRemover(c.coach_canonico)}
                            className="text-xs font-semibold text-white bg-red-600 hover:bg-red-700 px-2 py-1 rounded"
                          >
                            Confirmar remoção
                          </button>
                          <button
                            onClick={() => setConfirmandoRemocao(null)}
                            className="text-xs font-medium text-gray-600 hover:text-gray-800 px-2 py-1"
                          >
                            Cancelar
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => setFormState({ mode: "edit", coach: c })}
                            className="text-xs font-medium text-indigo-600 hover:text-indigo-800 px-2 py-1"
                          >
                            Editar
                          </button>
                          <button
                            onClick={() => setConfirmandoRemocao(c.coach_canonico)}
                            className="text-xs font-medium text-red-600 hover:text-red-800 px-2 py-1"
                          >
                            Remover
                          </button>
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      )}

      {formState && (
        <div
          data-testid="coach-cla-form-overlay"
          className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50"
        >
          <div className="bg-white rounded-xl shadow-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-bold text-gray-800 mb-4">
              {formState.mode === "add" ? "Adicionar coach" : `Editar ${formState.coach.coach_canonico}`}
            </h3>
            <CoachClaForm
              initialValues={
                formState.mode === "edit"
                  ? {
                      coach: formState.coach.coach_canonico,
                      clan: formState.coach.clan,
                      categoria: formState.coach.categoria,
                    }
                  : undefined
              }
              onSubmit={
                formState.mode === "add"
                  ? handleAdicionar
                  : (values) => handleEditar(formState.coach.coach_canonico, values)
              }
              onCancel={() => setFormState(null)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
