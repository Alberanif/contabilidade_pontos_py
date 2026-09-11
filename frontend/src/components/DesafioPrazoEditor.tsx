import React, { useState } from "react";
import { setDesafioPrazo } from "../api/client";

interface DesafioPrazoEditorProps {
  desafioId: number;
  prazoAtual: string | null;
  apuradoEm: string | null;
  onUpdate: () => void;
}

export const DesafioPrazoEditor: React.FC<DesafioPrazoEditorProps> = ({
  desafioId,
  prazoAtual,
  apuradoEm,
  onUpdate,
}) => {
  const [editing, setEditing] = useState(false);
  const [novoPrazo, setNovoPrazo] = useState(
    prazoAtual ? prazoAtual.slice(0, 16) : ""
  );
  const [loading, setLoading] = useState(false);

  const isApurado = Boolean(apuradoEm);
  const hasPrazo = Boolean(prazoAtual);

  const handleSave = async () => {
    try {
      setLoading(true);
      const isoPrazo = novoPrazo ? new Date(novoPrazo).toISOString() : null;
      await setDesafioPrazo(desafioId, isoPrazo);
      setEditing(false);
      onUpdate();
    } catch (err) {
      alert(`Erro ao salvar prazo: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setLoading(false);
    }
  };

  const handleClear = async () => {
    if (!confirm("Deseja remover o prazo deste desafio?")) return;
    try {
      setLoading(true);
      await setDesafioPrazo(desafioId, null);
      setEditing(false);
      onUpdate();
    } catch (err) {
      alert(`Erro ao remover prazo: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white border border-gray-200 shadow-sm rounded-xl p-4 mb-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <span className="text-gray-700 font-semibold text-sm">Prazo de Apuração:</span>
          {!editing ? (
            <div className="flex items-center gap-2">
              {isApurado ? (
                <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                  ✓ Apurado em {new Date(apuradoEm!).toLocaleString("pt-BR")}
                </span>
              ) : hasPrazo ? (
                <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
                  ⏳ Em andamento até {new Date(prazoAtual!).toLocaleString("pt-BR")}
                </span>
              ) : (
                <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                  ⚠️ Sem prazo definido (não apurado)
                </span>
              )}
            </div>
          ) : null}
        </div>

        {!editing ? (
          <button
            onClick={() => setEditing(true)}
            className="px-3 py-1.5 text-xs font-medium bg-gray-100 hover:bg-gray-200 text-gray-700 border border-gray-300 rounded-lg transition-colors"
          >
            {hasPrazo ? "Editar Prazo" : "Definir Prazo"}
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <input
              type="datetime-local"
              value={novoPrazo}
              onChange={(e) => setNovoPrazo(e.target.value)}
              className="bg-white border border-gray-300 text-gray-800 text-xs rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <button
              onClick={handleSave}
              disabled={loading}
              className="px-3 py-1.5 text-xs font-medium bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors disabled:opacity-50"
            >
              {loading ? "Salvando..." : "Salvar"}
            </button>
            {hasPrazo && (
              <button
                onClick={handleClear}
                disabled={loading}
                className="px-3 py-1.5 text-xs font-medium bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 rounded-lg transition-colors"
              >
                Remover
              </button>
            )}
            <button
              onClick={() => setEditing(false)}
              className="px-3 py-1.5 text-xs font-medium bg-gray-100 hover:bg-gray-200 text-gray-700 border border-gray-300 rounded-lg transition-colors"
            >
              Cancelar
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
