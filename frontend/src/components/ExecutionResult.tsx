import { useEffect, useState } from "react";
import { confirmarDesafios, type DesafioSyncResult } from "../api/client";

// Rótulos em pt-BR para as chaves de `state_counts` documentadas em
// `DesafioSyncResult` (backend/desafio_sync_service.py). A ordem aqui também
// define a ordem de exibição.
const STATE_LABELS: Record<string, string> = {
  new: "Novos",
  reappeared: "Reaparecidos",
  changed_with_effect: "Alterados (com efeito)",
  changed_without_effect: "Alterados (sem efeito)",
  unchanged: "Inalterados",
  missing: "Inativados",
  active_counted: "Ativos contabilizados",
  active_not_counted: "Ativos não contabilizados",
  invalid: "Inválidos",
  conflicted: "Conflitantes",
};

const STATE_ORDER = Object.keys(STATE_LABELS);

function formatDuration(seconds: number): string {
  return `${seconds.toFixed(1)}s`;
}

function formatPercent(ratio: number): string {
  return `${Math.round(ratio * 100)}%`;
}

function DeltaList({ deltas }: { deltas: Record<string, number> }) {
  const entries = Object.entries(deltas);
  if (entries.length === 0) {
    return <p className="text-gray-500">Nenhuma alteração nos clãs desde a última execução.</p>;
  }
  return (
    <ul className="space-y-0.5">
      {entries.map(([clan, delta]) => (
        <li key={clan} className="flex justify-between max-w-xs">
          <span className="text-gray-700">{clan}</span>
          <span className={delta >= 0 ? "font-semibold text-green-600" : "font-semibold text-red-600"}>
            {delta >= 0 ? "+" : ""}
            {delta}
          </span>
        </li>
      ))}
    </ul>
  );
}

export interface ExecutionResultProps {
  desafios: DesafioSyncResult;
  /** Chamado após uma confirmação bem-sucedida, para o pai atualizar outros dados (ex.: totais de clã). */
  onConfirmed?: (result: DesafioSyncResult) => void;
}

/**
 * Exibe o resultado da sincronização de desafios (Google Sheets) retornado por
 * `POST /api/contabilidade/executar`, e conduz o fluxo de confirmação de
 * remoção em massa (`POST /api/contabilidade/confirmar-desafios`) quando
 * `status === "awaiting_confirmation"`.
 *
 * Uma falha isolada de desafios (`status === "failed"`) é renderizada como
 * mais uma seção de erro dentro deste componente — nunca lança nem substitui
 * o restante da tela do chamador, que segue mostrando o resultado das outras
 * fontes (coaching, grupo, pro bono) normalmente.
 */
export default function ExecutionResult({ desafios, onConfirmed }: ExecutionResultProps) {
  const [current, setCurrent] = useState(desafios);
  const [confirming, setConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState("");

  // Se o pai executar uma nova contabilidade (novo `desafios` prop), o estado
  // interno acompanha o novo resultado em vez de continuar mostrando o antigo.
  useEffect(() => {
    setCurrent(desafios);
    setConfirmError("");
  }, [desafios]);

  const handleConfirmarRemocao = async () => {
    if (confirming || !current.snapshot_hash) return;
    setConfirming(true);
    setConfirmError("");
    try {
      const updated = await confirmarDesafios(current.snapshot_hash, true);
      setCurrent(updated);
      onConfirmed?.(updated);
    } catch (e) {
      setConfirmError(e instanceof Error ? e.message : "Erro ao confirmar remoção em massa");
    } finally {
      setConfirming(false);
    }
  };

  const stateEntries = STATE_ORDER.filter((key) => key in current.state_counts).map(
    (key) => [key, current.state_counts[key]] as const
  );

  return (
    <div className="mt-4 pt-4 border-t border-gray-100 space-y-3" data-testid="execution-result-desafios">
      <h4 className="text-sm font-semibold text-gray-700">Sincronização de Desafios (planilha)</h4>

      {current.status === "already_running" && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 px-4 py-3 rounded-lg text-sm">
          {current.mensagem || "Uma sincronização de desafios já está em andamento."}
        </div>
      )}

      {current.status === "failed" && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm space-y-1">
          <p className="font-medium">Falha ao sincronizar desafios: {current.mensagem}</p>
          <p>Execute a contabilidade novamente para revisar os dados atualizados.</p>
        </div>
      )}

      {current.status === "awaiting_confirmation" && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 px-4 py-3 rounded-lg text-sm space-y-2">
          <p className="font-medium">{current.mensagem}</p>
          <p>
            Tokens ativos antes: <strong>{current.active_tokens_before ?? 0}</strong>
          </p>
          <p>
            Tokens que deixariam de pontuar: <strong>{current.mass_removal_count}</strong> (
            <strong>{formatPercent(current.mass_removal_ratio)}</strong>)
          </p>
          <div>
            <p className="font-medium mb-1">Impacto por clã:</p>
            <DeltaList deltas={current.clan_deltas} />
          </div>
          {confirmError && <p className="text-red-700 font-medium">{confirmError}</p>}
          <button
            type="button"
            onClick={handleConfirmarRemocao}
            disabled={confirming || !current.snapshot_hash}
            className="bg-amber-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {confirming ? "Confirmando..." : "Confirmar remoção em massa"}
          </button>
        </div>
      )}

      {current.status === "success" && (
        <div className="text-sm text-gray-700 space-y-2">
          <p className="text-green-700 font-medium">{current.mensagem}</p>
          <p>
            Linhas na planilha: <strong>{current.sheet_row_count}</strong>
          </p>
          <p>
            Duração: <strong>{formatDuration(current.duration_seconds)}</strong>
          </p>

          {stateEntries.length > 0 && (
            <div>
              <p className="font-medium mb-1">Tokens por estado:</p>
              <ul className="space-y-0.5">
                {stateEntries.map(([key, count]) => (
                  <li key={key} className="flex justify-between max-w-xs">
                    <span className="text-gray-700">{STATE_LABELS[key] ?? key}</span>
                    <span className="font-semibold">{count}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <p>
            Transições de desafio: <strong>{current.challenges_created}</strong> criado(s),{" "}
            <strong>{current.challenges_archived}</strong> arquivado(s),{" "}
            <strong>{current.challenges_reactivated}</strong> reativado(s)
          </p>

          <div>
            <p className="font-medium mb-1">Deltas por clã:</p>
            <DeltaList deltas={current.clan_deltas} />
          </div>
        </div>
      )}
    </div>
  );
}
