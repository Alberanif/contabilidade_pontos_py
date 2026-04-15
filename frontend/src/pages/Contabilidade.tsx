import { useState } from "react";
import {
  executarContabilidade,
  reprocessarContabilidade,
  importarInicial,
  type ExecutarResponse,
  type ReprocessarResponse,
  type ImportarInicialResponse,
} from "../api/client";

export default function Contabilidade() {
  const [executing, setExecuting] = useState(false);
  const [reprocessing, setReprocessing] = useState(false);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<ExecutarResponse | ReprocessarResponse | null>(null);
  const [importResult, setImportResult] = useState<ImportarInicialResponse | null>(null);
  const [error, setError] = useState("");

  const handleExecutar = async () => {
    try {
      setExecuting(true);
      setError("");
      setResult(null);
      const data = await executarContabilidade();
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao executar");
    } finally {
      setExecuting(false);
    }
  };

  const handleImportar = async () => {
    if (!confirm("Isso vai apagar TODOS os dados existentes e reimportar tudo da planilha. Confirmar?")) return;
    try {
      setImporting(true);
      setError("");
      setImportResult(null);
      const data = await importarInicial();
      setImportResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao importar");
    } finally {
      setImporting(false);
    }
  };

  const handleReprocessar = async () => {
    if (!confirm("Tem certeza? Isso vai limpar TODOS os registros e reprocessar do zero.")) return;
    try {
      setReprocessing(true);
      setError("");
      setResult(null);
      const data = await reprocessarContabilidade();
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao reprocessar");
    } finally {
      setReprocessing(false);
    }
  };

  const isReprocessResult = (r: ExecutarResponse | ReprocessarResponse): r is ReprocessarResponse =>
    "registros_removidos" in r;

  const anyBusy = executing || reprocessing || importing;

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-800">Contabilidade</h2>

      {/* Configuração Inicial */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-6 space-y-3">
        <h3 className="text-base font-semibold text-blue-800">Configuração Inicial</h3>
        <p className="text-sm text-blue-700">
          Use este botão ao importar uma <strong>nova planilha</strong>. Apaga todos os dados
          existentes e reimporta tudo do zero: todos os registros são marcados como contabilizados,
          os totais dos clãs são lidos diretamente da planilha de pontuação, e o carry-over de
          grupo é configurado para futuras contabilizações.
        </p>
        <button
          onClick={handleImportar}
          disabled={anyBusy}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {importing ? "Importando..." : "Importar Dados Existentes"}
        </button>
        {importResult && (
          <div className="text-sm text-blue-800 bg-blue-100 rounded-lg px-4 py-3 space-y-1">
            <p className="font-medium">{importResult.mensagem}</p>
            <p>Registros removidos: <strong>{importResult.registros_removidos}</strong></p>
            <p>Coaching Individual importados: <strong>{importResult.coaching_individual_importados}</strong></p>
            <p>Grupo/Empresa contabilizados: <strong>{importResult.grupo_contabilizados}</strong></p>
            {importResult.grupo_pendentes > 0 && (
              <p className="text-amber-700">
                Grupo/Empresa na fila (aguardando lote): <strong>{importResult.grupo_pendentes}</strong>
              </p>
            )}
            {Object.keys(importResult.totais_clans).length > 0 && (
              <div className="mt-2">
                <p className="font-medium mb-1">Totais carregados da planilha:</p>
                <ul className="space-y-0.5">
                  {Object.entries(importResult.totais_clans).map(([clan, pts]) => (
                    <li key={clan} className="flex justify-between max-w-xs">
                      <span>{clan}</span>
                      <span className="font-semibold">{pts.toLocaleString("pt-BR")} pts</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-4">
          <h3 className="text-lg font-semibold text-gray-700">
            Executar Contagem
          </h3>
          <p className="text-sm text-gray-500">
            Busca novos registros na planilha. Coaching Individual: 30 pts por registro.
            Coaching em grupo / Empresa: 30 pts a cada 5 registros acumulados por clã (lote FIFO).
            Registros já processados são ignorados.
          </p>
          <button
            onClick={handleExecutar}
            disabled={anyBusy}
            className="bg-indigo-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors w-full"
          >
            {executing ? "Executando..." : "Executar Contagem"}
          </button>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-red-100 p-6 space-y-4">
          <h3 className="text-lg font-semibold text-gray-700">
            Reprocessar Tudo
          </h3>
          <p className="text-sm text-gray-500">
            Remove todos os registros contabilizados e reprocessa tudo do zero a
            partir da planilha. Use com cuidado.
          </p>
          <button
            onClick={handleReprocessar}
            disabled={anyBusy}
            className="bg-red-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors w-full"
          >
            {reprocessing ? "Reprocessando..." : "Reprocessar Tudo"}
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {result && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-3">
          <h3 className="text-lg font-semibold text-gray-700">
            Resultado da Execução
          </h3>
          <p className="text-green-700 font-medium">{result.mensagem}</p>

          {isReprocessResult(result) && (
            <p className="text-sm text-gray-600">
              Registros anteriores removidos: {result.registros_removidos}
            </p>
          )}

          <p className="text-sm text-gray-600">
            Coaching Individual contabilizados: <strong>{result.novos_registros}</strong>
          </p>
          <p className="text-sm text-gray-600">
            Grupo/Empresa adicionados à fila: <strong>{result.novos_pendentes}</strong>
          </p>

          {result.novos_registros > 0 && (
            <div>
              <p className="text-sm font-medium text-gray-600 mb-1">
                Pontos de Coaching Individual por clã:
              </p>
              <ul className="text-sm space-y-1">
                {Object.entries(result.pontos_por_clan).map(([clan, pontos]) => (
                  <li key={clan} className="flex justify-between max-w-xs">
                    <span className="text-gray-700">{clan}</span>
                    <span className="font-semibold text-indigo-600">+{pontos}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {Object.keys(result.pontos_grupo_por_clan ?? {}).length > 0 && (
            <div>
              <p className="text-sm font-medium text-gray-600 mb-1">
                Pontos de lotes completos (grupo/empresa) por clã:
              </p>
              <ul className="text-sm space-y-1">
                {Object.entries(result.pontos_grupo_por_clan).map(([clan, pontos]) => (
                  <li key={clan} className="flex justify-between max-w-xs">
                    <span className="text-gray-700">{clan}</span>
                    <span className="font-semibold text-green-600">+{pontos}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {Object.keys(result.pendentes_por_clan ?? {}).length > 0 && (
            <div>
              <p className="text-sm font-medium text-amber-700 mb-1">
                Registros pendentes aguardando lote completo (Clãs):
              </p>
              <ul className="text-sm space-y-1">
                {Object.entries(result.pendentes_por_clan).map(([clan, count]) => (
                  <li key={clan} className="flex justify-between max-w-xs">
                    <span className="text-gray-700">{clan}</span>
                    <span className="text-amber-600">
                      {count} registro{count !== 1 ? "s" : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {Object.keys(result.pontos_por_coach ?? {}).length > 0 && (
            <div className="mt-4 pt-4 border-t border-gray-100">
              <p className="text-sm font-medium text-gray-600 mb-1">
                Pontos de Coaching Individual por Coach:
              </p>
              <ul className="text-sm space-y-1">
                {Object.entries(result.pontos_por_coach).map(([coach, pontos]) => (
                  <li key={coach} className="flex justify-between max-w-xs">
                    <span className="text-gray-700">{coach}</span>
                    <span className="font-semibold text-indigo-600">+{pontos}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {Object.keys(result.pendentes_por_coach ?? {}).length > 0 && (
            <div className="mt-4">
              <p className="text-sm font-medium text-amber-700 mb-1">
                Fila de Coaches aguardando lote completo:
              </p>
              <ul className="text-sm space-y-1">
                {Object.entries(result.pendentes_por_coach).map(([coach, count]) => (
                  <li key={coach} className="flex justify-between max-w-xs">
                    <span className="text-gray-700">{coach}</span>
                    <span className="text-amber-600">
                      {count} pendente{count !== 1 ? "s" : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
