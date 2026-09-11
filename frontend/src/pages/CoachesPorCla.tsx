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

// Cor por categoria: mesmo nome de categoria sempre com a mesma cor, para que o
// olho identifique o papel do coach sem precisar ler o texto do badge —
// principalmente útil em clãs com muitos coaches na mesma tela.
const CATEGORIA_BADGE: Record<string, string> = {
  Coach: "bg-indigo-100 text-indigo-700",
  "Coach Action": "bg-sky-100 text-sky-700",
  "Coach Pro": "bg-violet-100 text-violet-700",
  "Coach Hero": "bg-amber-100 text-amber-700",
  "Sem Categoria": "bg-gray-100 text-gray-600",
  "Novos ULTIMATES": "bg-emerald-100 text-emerald-700",
};

function categoriaBadgeClass(categoria: string): string {
  return CATEGORIA_BADGE[categoria] ?? "bg-gray-100 text-gray-600";
}

// Quantos coaches mostrar por clã antes de exigir um clique em "Ver mais" —
// clãs reais têm ~20 coaches, e uma lista tão longa por padrão prejudicava a
// visão geral da tela (motivo da mudança).
const LIMITE_PADRAO_POR_CLA = 5;

export default function CoachesPorCla() {
  const [coaches, setCoaches] = useState<CoachCla[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState("");
  const [busca, setBusca] = useState("");
  const [formState, setFormState] = useState<FormState | null>(null);
  const [confirmandoRemocao, setConfirmandoRemocao] = useState<string | null>(null);
  // Clãs que o usuário expandiu manualmente além do limite padrão.
  const [clasExpandidos, setClasExpandidos] = useState<Set<string>>(new Set());

  function alternarExpandido(clan: string) {
    setClasExpandidos((atual) => {
      const proximo = new Set(atual);
      if (proximo.has(clan)) {
        proximo.delete(clan);
      } else {
        proximo.add(clan);
      }
      return proximo;
    });
  }

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
        <div className="space-y-5">
          {claOrdenados.map((clan) => {
            const coachesDoClan = grupos.get(clan) ?? [];
            // Busca ativa: mostra todos os resultados encontrados, sem
            // esconder atrás de "Ver mais" — o ponto de buscar é achar algo
            // específico rápido, não navegar por página.
            const buscaAtiva = normalizarBusca(busca) !== "";
            const expandido = buscaAtiva || clasExpandidos.has(clan);
            const temMais = coachesDoClan.length > LIMITE_PADRAO_POR_CLA;
            const coachesVisiveis = expandido
              ? coachesDoClan
              : coachesDoClan.slice(0, LIMITE_PADRAO_POR_CLA);
            return (
              <div
                key={clan}
                data-testid={`clan-section-${clan}`}
                className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden"
              >
                <div className="flex items-baseline justify-between gap-3 px-5 py-3 border-b border-gray-100 bg-gray-50/60">
                  <h3 className="text-sm font-bold text-gray-700 uppercase tracking-wide">{clan}</h3>
                  <span className="text-xs text-gray-400">
                    {coachesDoClan.length} {coachesDoClan.length === 1 ? "coach" : "coaches"}
                  </span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs font-medium text-gray-400 uppercase tracking-wide">
                        <th className="px-5 py-2 font-medium">Coach</th>
                        <th className="px-5 py-2 font-medium">Categoria</th>
                        <th className="px-5 py-2 font-medium text-right">Ações</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {coachesVisiveis.map((c) => (
                        <tr
                          key={c.coach_canonico}
                          data-testid={`coach-row-${c.coach_canonico}`}
                          className="hover:bg-gray-50 transition-colors"
                        >
                          <td className="px-5 py-2.5 font-medium text-gray-800 whitespace-nowrap">
                            {c.coach_canonico}
                          </td>
                          <td className="px-5 py-2.5">
                            <span
                              className={`inline-block px-2 py-0.5 rounded text-xs font-medium whitespace-nowrap ${categoriaBadgeClass(c.categoria)}`}
                            >
                              {c.categoria}
                            </span>
                          </td>
                          <td className="px-5 py-2.5 text-right">
                            {confirmandoRemocao === c.coach_canonico ? (
                              <div className="flex items-center justify-end gap-2 flex-wrap">
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
                              <div className="flex items-center justify-end gap-1">
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
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!buscaAtiva && temMais && (
                  <div className="px-5 py-2.5 border-t border-gray-100 bg-gray-50/40">
                    <button
                      onClick={() => alternarExpandido(clan)}
                      className="text-xs font-semibold text-indigo-600 hover:text-indigo-800"
                    >
                      {expandido
                        ? "Ver menos"
                        : `Ver mais (${coachesDoClan.length - LIMITE_PADRAO_POR_CLA})`}
                    </button>
                  </div>
                )}
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
