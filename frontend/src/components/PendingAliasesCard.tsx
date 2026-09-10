import { useState, useEffect } from "react";
import {
  type PendingAlias,
  fetchPendingAliases,
  triggerSugerirAliasesLLM,
  aprovarAliasPendente,
  rejeitarAliasPendente,
} from "../api/client";


interface PendingAliasesCardProps {
  onAliasApproved?: () => void;
}

export default function PendingAliasesCard({ onAliasApproved }: PendingAliasesCardProps) {
  const [items, setItems] = useState<PendingAlias[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [analyzing, setAnalyzing] = useState<boolean>(false);
  const [edits, setEdits] = useState<Record<number, string>>({});
  const [message, setMessage] = useState<string | null>(null);

  const loadPending = async () => {
    setLoading(true);
    try {
      const data = await fetchPendingAliases("pendente");
      setItems(data);
      // Inicializa edições locais com a sugestão atual
      const initialEdits: Record<number, string> = {};
      data.forEach((item) => {
        initialEdits[item.id] = item.coach_sugerido;
      });
      setEdits(initialEdits);
    } catch (err: any) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPending();
  }, []);

  const handleAnalyze = async () => {
    setAnalyzing(true);
    setMessage(null);
    try {
      const res = await triggerSugerirAliasesLLM();
      setMessage(res.mensagem);
      await loadPending();
      if (onAliasApproved && res.auto_aprovados > 0) {
        onAliasApproved();
      }
    } catch (err: any) {
      setMessage(`Erro ao analisar: ${err.message}`);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleApprove = async (id: number) => {
    try {
      const override = edits[id];
      const res = await aprovarAliasPendente(id, override);
      setMessage(res.mensagem);
      await loadPending();
      if (onAliasApproved) {
        onAliasApproved();
      }
    } catch (err: any) {
      setMessage(`Erro ao aprovar: ${err.message}`);
    }
  };

  const handleReject = async (id: number) => {
    try {
      const res = await rejeitarAliasPendente(id);
      setMessage(res.mensagem);
      await loadPending();
    } catch (err: any) {
      setMessage(`Erro ao rejeitar: ${err.message}`);
    }
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <h3 className="text-lg font-bold text-gray-800">
            Sugestões de Aliases (IA / Groq)
          </h3>
          {items.length > 0 && (
            <span className="bg-amber-100 text-amber-800 text-xs font-semibold px-2.5 py-0.5 rounded-full">
              {items.length} pendente(s)
            </span>
          )}
        </div>
        <button
          onClick={handleAnalyze}
          disabled={analyzing}
          className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-2 rounded-lg shadow-sm transition-colors disabled:opacity-50 flex items-center gap-2"
        >
          {analyzing ? (
            <>
              <span className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
              Analisando com IA...
            </>
          ) : (
            <>✨ Analisar Nomes com IA</>
          )}
        </button>
      </div>

      {message && (
        <div className="bg-blue-50 text-blue-800 text-sm p-3 rounded-lg border border-blue-200">
          {message}
        </div>
      )}

      {loading ? (
        <div className="text-center py-6 text-gray-500 text-sm">Carregando sugestões...</div>
      ) : items.length === 0 ? (
        <div className="text-center py-6 text-gray-400 text-sm bg-gray-50 rounded-lg border border-dashed border-gray-200">
          Nenhum alias pendente de revisão no momento. Todos os nomes estão resolvidos!
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-gray-600">
            <thead className="bg-gray-50 text-gray-700 font-semibold border-b border-gray-200">
              <tr>
                <th className="py-3 px-4">Nome Digitado (Raw)</th>
                <th className="py-3 px-4">Sugestão da IA (Canônico)</th>
                <th className="py-3 px-4">Confiança</th>
                <th className="py-3 px-4">Origem</th>
                <th className="py-3 px-4 text-right">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {items.map((item) => {
                const isHighConf = item.confianca >= 90;
                return (
                  <tr key={item.id} className="hover:bg-gray-50 transition-colors">
                    <td className="py-3 px-4 font-medium text-gray-900">
                      {item.alias_raw}
                    </td>
                    <td className="py-3 px-4">
                      <input
                        type="text"
                        value={edits[item.id] ?? item.coach_sugerido}
                        onChange={(e) =>
                          setEdits({ ...edits, [item.id]: e.target.value })
                        }
                        className="bg-white border border-gray-300 rounded px-2.5 py-1 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 w-full max-w-xs"
                      />
                    </td>
                    <td className="py-3 px-4">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold ${
                          isHighConf
                            ? "bg-green-100 text-green-800"
                            : "bg-amber-100 text-amber-800"
                        }`}
                      >
                        {item.confianca}%
                      </span>
                    </td>
                    <td className="py-3 px-4 text-xs text-gray-500 uppercase tracking-wider">
                      {item.origem}
                    </td>
                    <td className="py-3 px-4 text-right flex items-center justify-end gap-2">
                      <button
                        onClick={() => handleApprove(item.id)}
                        className="bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold px-3 py-1.5 rounded transition-colors"
                      >
                        Aprovar
                      </button>
                      <button
                        onClick={() => handleReject(item.id)}
                        className="bg-gray-200 hover:bg-gray-300 text-gray-700 text-xs font-medium px-3 py-1.5 rounded transition-colors"
                      >
                        Rejeitar
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
