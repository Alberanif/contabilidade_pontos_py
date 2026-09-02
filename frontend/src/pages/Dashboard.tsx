import { useEffect, useState } from "react";
import {
  fetchClans,
  fetchRanking,
  fetchCoaches,
  fetchHistorico,
  fetchTotaisPorTipo,
  executarContabilidade,
  atualizarPlanilha,
  type ClanTotal,
  type CoachTotal,
  type RankingEntry,
  type ExecutarResponse,
  type HistoricoResponse,
} from "../api/client";
import ClanCard from "../components/ClanCard";
import PendingAliasesCard from "../components/PendingAliasesCard";

const MEDAL: Record<number, string> = { 1: "🥇", 2: "🥈", 3: "🥉" };


type TipoFiltro = "todos" | "pagante" | "pro_bono" | "desafios";

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState<"clans" | "coaches">("clans");

  const [clans, setClans] = useState<ClanTotal[]>([]);
  const [coaches, setCoaches] = useState<CoachTotal[]>([]);
  const [ranking, setRanking] = useState<RankingEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingRanking, setLoadingRanking] = useState(true);
  const [executing, setExecuting] = useState(false);
  const [result, setResult] = useState<ExecutarResponse | null>(null);
  const [updatingSheet, setUpdatingSheet] = useState(false);
  const [sheetMessage, setSheetMessage] = useState("");
  const [error, setError] = useState("");

  const [dataInicio, setDataInicio] = useState<string>("");
  const [dataFim, setDataFim] = useState<string>("");
  const [historicoData, setHistoricoData] = useState<HistoricoResponse | null>(null);
  const [loadingHistorico, setLoadingHistorico] = useState(false);

  const [tipoFiltro, setTipoFiltro] = useState<TipoFiltro>("todos");
  const [tipoData, setTipoData] = useState<HistoricoResponse | null>(null);
  const [loadingTipo, setLoadingTipo] = useState(false);

  const loadData = async () => {
    try {
      setLoading(true);
      const [clansData, coachesData] = await Promise.all([
        fetchClans(),
        fetchCoaches(),
      ]);
      setClans(clansData);
      setCoaches(coachesData);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao carregar dados");
    } finally {
      setLoading(false);
    }
  };

  const loadRanking = async () => {
    try {
      setLoadingRanking(true);
      const data = await fetchRanking();
      setRanking(data);
    } catch {
      // ranking é opcional; não bloqueia o resto da página
    } finally {
      setLoadingRanking(false);
    }
  };

  useEffect(() => {
    loadData();
    loadRanking();
  }, []);

  useEffect(() => {
    if (!dataInicio || !dataFim || tipoFiltro !== "todos") {
      return; // Don't fetch if either date is empty or type filter is active
    }

    if (dataInicio > dataFim) {
      console.warn("Data início deve ser anterior a data fim");
      return; // Don't fetch if dates are inverted
    }

    const applyFilter = async () => {
      try {
        setLoadingHistorico(true);
        setError("");
        const data = await fetchHistorico(dataInicio, dataFim);
        setHistoricoData(data);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erro ao carregar histórico");
        setHistoricoData(null);
      } finally {
        setLoadingHistorico(false);
      }
    };

    applyFilter();
  }, [dataInicio, dataFim, tipoFiltro]);

  useEffect(() => {
    if (tipoFiltro === "todos") {
      setTipoData(null);
      return;
    }
    const fetchData = async () => {
      try {
        setLoadingTipo(true);
        setError("");
        const data = await fetchTotaisPorTipo(
          tipoFiltro,
          dataInicio || undefined,
          dataFim || undefined
        );
        setTipoData(data);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erro ao carregar dados por tipo");
        setTipoData(null);
      } finally {
        setLoadingTipo(false);
      }
    };
    fetchData();
  }, [tipoFiltro, dataInicio, dataFim]);

  const activeData = tipoFiltro !== "todos" ? tipoData : historicoData;

  const handleAtualizarPlanilha = async () => {
    try {
      setUpdatingSheet(true);
      setSheetMessage("");
      setError("");
      const data = await atualizarPlanilha();
      setSheetMessage(data.mensagem);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao atualizar planilha");
    } finally {
      setUpdatingSheet(false);
    }
  };

  const handleExecutar = async () => {
    try {
      setExecuting(true);
      setError("");
      setResult(null);
      const data = await executarContabilidade();
      setResult(data);
      await Promise.all([loadData(), loadRanking()]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao executar contabilidade");
    } finally {
      setExecuting(false);
    }
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-gray-800">Dashboard</h2>
        <div className="flex gap-3">
          <button
            onClick={handleAtualizarPlanilha}
            disabled={updatingSheet}
            className="bg-green-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {updatingSheet ? "Atualizando..." : "Atualizar Planilha"}
          </button>
          <button
            onClick={handleExecutar}
            disabled={executing}
            className="bg-indigo-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {executing ? "Executando..." : "Executar Contabilidade"}
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      <div className="flex gap-2 flex-wrap mb-4">
        {(["todos", "pagante", "pro_bono", "desafios"] as TipoFiltro[]).map((t) => {
          const labels: Record<TipoFiltro, string> = {
            todos: "Todos",
            pagante: "Pagantes",
            pro_bono: "Pro Bono",
            desafios: "Desafios",
          };
          return (
            <button
              key={t}
              onClick={() => setTipoFiltro(t)}
              className={`px-4 py-1.5 rounded-full text-sm font-medium border transition-colors ${
                tipoFiltro === t
                  ? "bg-indigo-600 text-white border-indigo-600"
                  : "bg-white text-gray-600 border-gray-300 hover:border-indigo-400"
              }`}
            >
              {labels[t]}
            </button>
          );
        })}
      </div>

      <div className="flex gap-4 items-end mb-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            De:
          </label>
          <input
            type="date"
            value={dataInicio}
            onChange={(e) => setDataInicio(e.target.value)}
            className="px-4 py-2 border border-gray-300 rounded-lg"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Até:
          </label>
          <input
            type="date"
            value={dataFim}
            onChange={(e) => setDataFim(e.target.value)}
            className="px-4 py-2 border border-gray-300 rounded-lg"
          />
        </div>
        <button
          onClick={() => {
            setDataInicio("");
            setDataFim("");
            setHistoricoData(null);
          }}
          className="px-4 py-2 bg-gray-300 text-gray-800 rounded-lg hover:bg-gray-400"
        >
          Limpar filtro
        </button>
      </div>

      {activeData && (tipoFiltro !== "todos" || (dataInicio && dataFim)) && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 px-4 py-2 rounded-lg text-sm">
          {tipoFiltro !== "todos" && (
            <>
              Visualizando <strong>{tipoFiltro.charAt(0).toUpperCase() + tipoFiltro.slice(1) === "Pagante" ? "Pagantes" : tipoFiltro === "pro_bono" ? "Pro Bono" : "Desafios"}</strong>
              {dataInicio && dataFim && (
                <>
                  {" "}de{" "}
                  <strong>
                    {new Date(dataInicio + "T00:00:00").toLocaleDateString("pt-BR")}
                  </strong>
                  {" "}até{" "}
                  <strong>
                    {new Date(dataFim + "T00:00:00").toLocaleDateString("pt-BR")}
                  </strong>
                </>
              )}
              .
            </>
          )}
          {tipoFiltro === "todos" && dataInicio && dataFim && (
            <>
              Visualizando período de{" "}
              <strong>
                {new Date(dataInicio + "T00:00:00").toLocaleDateString("pt-BR")}
              </strong>
              {" "}até{" "}
              <strong>
                {new Date(dataFim + "T00:00:00").toLocaleDateString("pt-BR")}
              </strong>
              .
            </>
          )}
          {" Os valores abaixo refletem os dados filtrados."}
        </div>
      )}

      {(loadingHistorico || loadingTipo) && (
        <p className="text-gray-500 text-sm">Carregando dados...</p>
      )}

      {sheetMessage && (
        <div className="bg-blue-50 border border-blue-200 text-blue-700 px-4 py-3 rounded-lg">
          {sheetMessage}
        </div>
      )}

      {result && (
        <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg">
          <p className="font-medium">{result.mensagem}</p>
          {result.novos_registros > 0 && (
            <ul className="mt-2 text-sm space-y-1">
              {Object.entries(result.pontos_por_clan).map(([clan, pontos]) => (
                <li key={clan}>
                  {clan}: +{pontos} pontos
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="border-b border-gray-200 mb-6">
        <nav className="-mb-px flex space-x-8" aria-label="Tabs">
          <button
            onClick={() => setActiveTab("clans")}
            className={`whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm ${
              activeTab === "clans"
                ? "border-indigo-500 text-indigo-600"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
            }`}
          >
            Clãs
          </button>
          <button
            onClick={() => setActiveTab("coaches")}
            className={`whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm ${
              activeTab === "coaches"
                ? "border-indigo-500 text-indigo-600"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
            }`}
          >
            Coaches
          </button>
        </nav>
      </div>

      {activeTab === "clans" && (
        <>
          {loading ? (
            <p className="text-gray-500">Carregando clãs...</p>
          ) : clans.length > 0 && (
            <div>
              <h3 className="text-lg font-semibold text-gray-700 mb-3">Pontos por Clã</h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
                {(activeData
                  ? Object.entries(activeData.clans).map(([clan, total_pontos], idx) => ({
                      id: idx,
                      clan,
                      total_pontos,
                    }))
                  : clans
                ).map((c) => (
                  <ClanCard key={c.clan} clan={c.clan} totalPontos={c.total_pontos} />
                ))}
              </div>
            </div>
          )}

          <div className="mt-8">
            <h3 className="text-lg font-semibold text-gray-700 mb-3">Ranking Geral de Clãs</h3>
            {loading || loadingRanking ? (
              <p className="text-gray-500">Carregando ranking...</p>
            ) : clans.length === 0 ? (
              <p className="text-gray-500">Nenhum dado de ranking disponível.</p>
            ) : (() => {
              const nomeMap: Record<string, string> = {};
              for (const entry of ranking) {
                nomeMap[entry.clan] = entry.nome_completo;
              }

              const clanSource: { clan: string; total_pontos: number }[] =
                activeData
                  ? Object.entries(activeData.clans).map(([clan, total_pontos]) => ({
                      clan,
                      total_pontos,
                    }))
                  : clans.map((c) => ({ clan: c.clan, total_pontos: c.total_pontos }));

              const sorted = [...clanSource]
                .sort((a, b) => b.total_pontos - a.total_pontos)
                .map((c, idx) => ({
                  posicao: idx + 1,
                  clan: c.clan,
                  nome_completo: nomeMap[c.clan] ?? "",
                  total_pontos: c.total_pontos,
                }));

              return (
                <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-gray-50 border-b border-gray-200 text-left text-gray-500">
                        <th className="py-3 px-4 font-medium w-12 text-center">Pos.</th>
                        <th className="py-3 px-4 font-medium">Clã</th>
                        <th className="py-3 px-4 font-medium">Líder</th>
                        <th className="py-3 px-4 font-medium text-right">Pontos</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sorted.map((entry) => (
                        <tr key={entry.clan} className="border-b border-gray-100 hover:bg-gray-50">
                          <td className="py-3 px-4 text-center font-bold text-lg">
                            {MEDAL[entry.posicao] ?? `#${entry.posicao}`}
                          </td>
                          <td className="py-3 px-4 font-medium text-gray-700">{entry.clan}</td>
                          <td className="py-3 px-4 text-gray-600">{entry.nome_completo}</td>
                          <td className="py-3 px-4 text-right font-bold text-indigo-600 text-base">
                            {entry.total_pontos.toLocaleString("pt-BR")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              );
            })()}
          </div>
        </>
      )}

      {activeTab === "coaches" && (
        <div className="mt-8 space-y-6">
          <PendingAliasesCard onAliasApproved={loadData} />

          <div>
            <h3 className="text-lg font-semibold text-gray-700 mb-3">Ranking de Coaches</h3>

          {loading ? (
            <p className="text-gray-500">Carregando coaches...</p>
          ) : (activeData ? Object.keys(activeData.coaches).length === 0 : coaches.length === 0) ? (
            <p className="text-gray-500">Nenhum dado disponível.</p>
          ) : (() => {
            const coachSource: { coach: string; total_pontos: number }[] =
              activeData
                ? Object.entries(activeData.coaches).map(([coach, total_pontos]) => ({
                    coach,
                    total_pontos,
                  }))
                : coaches.map((c) => ({ coach: c.coach, total_pontos: c.total_pontos }));

            const sorted = [...coachSource]
              .sort((a, b) => b.total_pontos - a.total_pontos)
              .map((c, idx) => ({
                posicao: idx + 1,
                coach: c.coach,
                total_pontos: c.total_pontos,
              }));

            return (
              <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-200 text-left text-gray-500">
                      <th className="py-3 px-4 font-medium w-12 text-center">Pos.</th>
                      <th className="py-3 px-4 font-medium">Coach</th>
                      <th className="py-3 px-4 font-medium text-right">Pontos</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map((entry) => (
                      <tr key={entry.coach} className="border-b border-gray-100 hover:bg-gray-50">
                        <td className="py-3 px-4 text-center font-bold text-lg">
                          {MEDAL[entry.posicao] ?? `#${entry.posicao}`}
                        </td>
                        <td className="py-3 px-4 font-medium text-gray-700">{entry.coach}</td>
                        <td className="py-3 px-4 text-right font-bold text-indigo-600 text-base">
                          {entry.total_pontos.toLocaleString("pt-BR")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          })()}
          </div>
        </div>
      )}
    </div>
  );
}

