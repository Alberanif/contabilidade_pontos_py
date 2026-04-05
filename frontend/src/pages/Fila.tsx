import { useEffect, useState } from "react";
import {
  fetchRegistros,
  fetchClans,
  aprovarClan,
  type Registro,
  type ClanTotal,
  type AprovarClanResponse,
} from "../api/client";

const BATCH_SIZE = 5;
const POINTS_PER_BATCH = 30;

interface ClanGroup {
  clan: string;
  registros: Registro[];
  pessoasNovos: number;
  carryOver: number;
  totalPessoas: number;
  lotesCompletos: number;
  pontosDisponiveis: number;
  pessoasEmEspera: number;
}

function getNumParticipantes(r: Registro): number {
  return r.num_participantes > 0 ? r.num_participantes : 1;
}

function getSubmittedAt(raw_data: string): string {
  try {
    const data = JSON.parse(raw_data);
    return data["Submitted At"] || data["Submitted at"] || "";
  } catch {
    return "";
  }
}

function getCoach(raw_data: string): string {
  try {
    const data = JSON.parse(raw_data);
    return (
      data["Nome do Coach responsável pelo atendimento:"] ||
      data["Nome do Coach responsável pelo atendimento"] ||
      ""
    );
  } catch {
    return "";
  }
}

export default function Fila() {
  const [groups, setGroups] = useState<ClanGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [aprovando, setAprovando] = useState<string | null>(null);
  const [resultado, setResultado] = useState<Record<string, AprovarClanResponse>>({});

  const load = async () => {
    try {
      setLoading(true);
      setError("");
      const [registrosData, clansData] = await Promise.all([
        fetchRegistros({ status: "pendente", limit: 200 }),
        fetchClans(),
      ]);

      const clanMap = new Map<string, ClanTotal>(
        clansData.map((c) => [c.clan, c])
      );

      const byClan: Record<string, Registro[]> = {};
      for (const r of registrosData.registros) {
        if (!byClan[r.clan]) byClan[r.clan] = [];
        byClan[r.clan].push(r);
      }

      const grouped: ClanGroup[] = Object.entries(byClan)
        .map(([clan, registros]) => {
          const pessoasNovos = registros.reduce(
            (sum, r) => sum + getNumParticipantes(r),
            0
          );
          const carryOver = clanMap.get(clan)?.pessoas_em_espera ?? 0;
          const totalPessoas = carryOver + pessoasNovos;
          const lotesCompletos = Math.floor(totalPessoas / BATCH_SIZE);
          return {
            clan,
            registros,
            pessoasNovos,
            carryOver,
            totalPessoas,
            lotesCompletos,
            pontosDisponiveis: lotesCompletos * POINTS_PER_BATCH,
            pessoasEmEspera: totalPessoas % BATCH_SIZE,
          };
        })
        .sort((a, b) => b.totalPessoas - a.totalPessoas);

      setGroups(grouped);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao carregar fila");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleAprovar = async (clan: string) => {
    try {
      setAprovando(clan);
      const res = await aprovarClan(clan);
      setResultado((prev) => ({ ...prev, [clan]: res }));
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao aprovar");
    } finally {
      setAprovando(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-800">Fila de Aprovação</h2>
          <p className="text-sm text-gray-500 mt-1">
            Registros de Coaching em grupo e Coaching em Empresa aguardando aprovação.
            A cada 5 pessoas atendidas, o clã recebe 30 pontos.
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="text-sm text-indigo-600 hover:text-indigo-800 font-medium"
        >
          Atualizar
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-gray-500">Carregando fila...</p>
      ) : groups.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-8 text-center text-gray-500">
          Nenhum registro pendente na fila.
        </div>
      ) : (
        <div className="space-y-6">
          {groups.map((g) => {
            const res = resultado[g.clan];
            const faltam = BATCH_SIZE - g.pessoasEmEspera;
            return (
              <div
                key={g.clan}
                className="bg-white rounded-xl border border-gray-200 overflow-hidden"
              >
                {/* Cabeçalho do clã */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 bg-gray-50">
                  <div className="flex items-center gap-3 flex-wrap">
                    <h3 className="text-lg font-bold text-gray-800">{g.clan}</h3>
                    <span className="text-sm text-gray-500">
                      {g.registros.length} registro{g.registros.length !== 1 ? "s" : ""}
                    </span>
                    <span className="text-sm font-semibold text-indigo-600">
                      {g.pessoasNovos} pessoa{g.pessoasNovos !== 1 ? "s" : ""}
                    </span>
                    {g.carryOver > 0 && (
                      <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-medium">
                        +{g.carryOver} do ciclo anterior
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-4">
                    <div className="text-right text-sm">
                      {g.lotesCompletos > 0 ? (
                        <span className="text-green-700 font-medium">
                          {g.totalPessoas} pessoas → +{g.pontosDisponiveis} pts
                        </span>
                      ) : (
                        <span className="text-amber-600">
                          faltam {faltam} pessoa{faltam !== 1 ? "s" : ""} para o próximo lote
                        </span>
                      )}
                      <span
                        className={`block text-xs mt-0.5 font-medium ${
                          g.pessoasEmEspera > 0 ? "text-amber-600" : "text-gray-400"
                        }`}
                      >
                        Saldo em espera:{" "}
                        <strong>{g.pessoasEmEspera}</strong> pessoa{g.pessoasEmEspera !== 1 ? "s" : ""}
                      </span>
                    </div>

                    {g.lotesCompletos > 0 && (
                      <button
                        onClick={() => handleAprovar(g.clan)}
                        disabled={aprovando === g.clan}
                        className="bg-green-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
                      >
                        {aprovando === g.clan
                          ? "Aprovando..."
                          : `Aprovar (+${g.pontosDisponiveis} pts)`}
                      </button>
                    )}
                  </div>
                </div>

                {/* Resultado da aprovação */}
                {res && (
                  <div className="px-6 py-3 bg-green-50 border-b border-green-100 text-sm text-green-700 font-medium">
                    ✓ {res.mensagem}
                    {res.pessoas_em_espera > 0 && (
                      <span className="ml-2 text-amber-600">
                        · {res.pessoas_em_espera} pessoa{res.pessoas_em_espera !== 1 ? "s" : ""} em espera para o próximo ciclo.
                      </span>
                    )}
                  </div>
                )}

                {/* Lista de registros */}
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-gray-500 border-b border-gray-100">
                        <th className="py-2 px-4 font-medium w-8">#</th>
                        <th className="py-2 px-4 font-medium">Modalidade</th>
                        <th className="py-2 px-4 font-medium">Coach</th>
                        <th className="py-2 px-4 font-medium text-center">Pessoas</th>
                        <th className="py-2 px-4 font-medium">Submitted At</th>
                      </tr>
                    </thead>
                    <tbody>
                      {g.registros.map((r, idx) => (
                        <tr
                          key={r.id}
                          className={`border-b border-gray-50 ${
                            g.lotesCompletos > 0
                              ? "bg-green-50/40"
                              : "bg-amber-50/30"
                          }`}
                        >
                          <td className="py-2 px-4 text-gray-400">{idx + 1}</td>
                          <td className="py-2 px-4 text-gray-700">{r.modalidade}</td>
                          <td className="py-2 px-4 text-gray-700">
                            {getCoach(r.raw_data) || "—"}
                          </td>
                          <td className="py-2 px-4 text-center font-semibold text-indigo-700">
                            {getNumParticipantes(r)}
                          </td>
                          <td className="py-2 px-4 text-gray-500">
                            {getSubmittedAt(r.raw_data) || "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className="border-t border-gray-200 bg-gray-50 font-semibold text-sm">
                        <td className="py-2 px-4 text-gray-500" colSpan={3}>
                          Total de pessoas nos registros
                        </td>
                        <td className="py-2 px-4 text-center text-indigo-700">
                          {g.pessoasNovos}
                        </td>
                        <td className="py-2 px-4" />
                      </tr>
                    </tfoot>
                  </table>
                </div>

                {/* Rodapé: legenda + saldo */}
                <div className="px-4 py-3 flex items-center justify-between border-t border-gray-100 bg-gray-50 text-xs text-gray-500">
                  <span className="flex items-center gap-1">
                    {g.lotesCompletos > 0 ? (
                      <>
                        <span className="w-3 h-3 rounded-sm bg-green-100 inline-block" />
                        Todos os registros serão aprovados juntos
                      </>
                    ) : (
                      <>
                        <span className="w-3 h-3 rounded-sm bg-amber-100 inline-block" />
                        Acumulando pessoas para completar o próximo lote
                      </>
                    )}
                  </span>
                  <span
                    className={`font-semibold ${
                      g.pessoasEmEspera > 0 ? "text-amber-600" : "text-gray-400"
                    }`}
                  >
                    Saldo em espera após aprovação:{" "}
                    <strong>{g.pessoasEmEspera}</strong> pessoa{g.pessoasEmEspera !== 1 ? "s" : ""}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
