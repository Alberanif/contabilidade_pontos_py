import React from "react";
import type { DesafioApuracaoResponse } from "../api/client";

interface DesafioClanApuracaoTableProps {
  apuracao: DesafioApuracaoResponse | null;
  loading: boolean;
}

export const DesafioClanApuracaoTable: React.FC<DesafioClanApuracaoTableProps> = ({
  apuracao,
  loading,
}) => {
  if (loading) {
    return (
      <div className="bg-white border border-gray-200 shadow-sm rounded-xl p-6 mb-6 text-center text-gray-500 text-sm">
        Carregando apuração do clã...
      </div>
    );
  }

  if (!apuracao || !apuracao.clas || apuracao.clas.length === 0) {
    return (
      <div className="bg-white border border-gray-200 shadow-sm rounded-xl p-6 mb-6 text-center text-gray-500 text-sm">
        Nenhuma apuração de engajamento disponível para este desafio.
      </div>
    );
  }

  const isProvisorio = apuracao.provisorio;

  return (
    <div className="bg-white border border-gray-200 shadow-sm rounded-xl p-5 mb-6">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div>
          <h3 className="text-base font-semibold text-gray-800 flex items-center gap-2">
            🏆 Pontuação por Engajamento do Clã
          </h3>
          <p className="text-xs text-gray-500 mt-0.5">
            Pontos atribuídos de acordo com o percentual de coaches aprovados no clã.
          </p>
        </div>
        <div>
          {isProvisorio ? (
            <span className="px-3 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
              📊 Prévia (não definitiva)
            </span>
          ) : (
            <span className="px-3 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
              ✅ Apuração Final Consolidada
            </span>
          )}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm text-gray-700">
          <thead className="text-xs uppercase bg-gray-50 text-gray-500 font-semibold border-b border-gray-200">
            <tr>
              <th className="py-2.5 px-3">Clã</th>
              <th className="py-2.5 px-3">Participantes / Total Grupo</th>
              <th className="py-2.5 px-3">% Participação</th>
              <th className="py-2.5 px-3 text-right">Pontos</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {apuracao.clas.map((c) => (
              <tr key={c.clan} className="hover:bg-gray-50/80 transition-colors">
                <td className="py-2.5 px-3 font-semibold text-gray-800">{c.clan}</td>
                <td className="py-2.5 px-3">
                  <span className="font-semibold text-gray-900">{c.participantes}</span>
                  <span className="text-gray-400"> / {c.total_grupo}</span>
                </td>
                <td className="py-2.5 px-3">
                  <div className="flex items-center gap-2">
                    <div className="w-24 bg-gray-100 rounded-full h-2 overflow-hidden border border-gray-200">
                      <div
                        className={`h-full rounded-full ${
                          c.percentual >= 50
                            ? "bg-emerald-500"
                            : c.percentual >= 10
                            ? "bg-indigo-500"
                            : "bg-gray-400"
                        }`}
                        style={{ width: `${Math.min(100, c.percentual)}%` }}
                      />
                    </div>
                    <span className="font-mono text-xs font-medium text-gray-700">
                      {c.percentual.toFixed(1)}%
                    </span>
                  </div>
                </td>
                <td className="py-2.5 px-3 text-right font-bold text-emerald-600">
                  +{c.pontos} pts
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
