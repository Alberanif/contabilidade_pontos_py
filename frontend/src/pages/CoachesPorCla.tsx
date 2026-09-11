import { useEffect, useMemo, useState } from "react";
import { fetchCoachClas, type CoachCla } from "../api/client";

// Página "Coaches por Clã" (issue #6, PRD #28) — listagem somente leitura da
// atribuição fixa de cada coach a um único clã. Não existe aqui nenhuma ação
// de adicionar/editar/mover/remover coach de clã (fica para a issue #7) nem
// exibição de pontos/totais (fora de escopo desta tela).

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

export default function CoachesPorCla() {
  const [coaches, setCoaches] = useState<CoachCla[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState("");
  const [busca, setBusca] = useState("");

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
                      className="py-2 flex items-center justify-between gap-2"
                    >
                      <span className="text-sm font-medium text-gray-800">{c.coach_canonico}</span>
                      <span className="px-2 py-0.5 rounded text-xs font-medium bg-indigo-100 text-indigo-700 whitespace-nowrap">
                        {c.categoria}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
