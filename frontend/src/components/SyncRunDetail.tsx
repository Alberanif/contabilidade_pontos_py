import type { DesafioSincronizacao } from "../api/client";

// Rótulos em pt-BR para `DesafioSyncRunResponse.status`
// (backend/routers/desafio_auditoria.py).
const SYNC_STATUS_LABELS: Record<string, string> = {
  running: "Em execução",
  succeeded: "Sucesso",
  failed: "Falhou",
  awaiting_confirmation: "Aguardando confirmação",
  cancelled: "Cancelada",
};

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("pt-BR");
}

function DeltaList({ deltas }: { deltas: Record<string, number> }) {
  const entries = Object.entries(deltas);
  if (entries.length === 0) {
    return <p className="text-gray-500 text-sm">Nenhuma alteração nos clãs.</p>;
  }
  return (
    <ul className="space-y-0.5 text-sm">
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

export interface SyncRunDetailProps {
  execucao: DesafioSincronizacao;
}

/** Detalhe somente leitura de uma execução de sincronização da Google Sheet. */
export default function SyncRunDetail({ execucao }: SyncRunDetailProps) {
  const stateEntries = Object.entries(execucao.state_counts);
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4 text-sm" data-testid="sync-run-detail">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="text-lg font-bold text-gray-800">Execução #{execucao.id}</h3>
        <span className="px-2 py-0.5 rounded text-xs font-medium bg-indigo-100 text-indigo-700">
          {SYNC_STATUS_LABELS[execucao.status] ?? execucao.status}
        </span>
      </div>

      <dl className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <div>
          <dt className="text-gray-500">Iniciada em</dt>
          <dd className="font-medium text-gray-800">{formatDateTime(execucao.started_at)}</dd>
        </div>
        <div>
          <dt className="text-gray-500">Finalizada em</dt>
          <dd className="font-medium text-gray-800">{formatDateTime(execucao.finished_at)}</dd>
        </div>
        <div>
          <dt className="text-gray-500">Linhas na planilha</dt>
          <dd className="font-medium text-gray-800">{execucao.sheet_row_count}</dd>
        </div>
        <div>
          <dt className="text-gray-500">Pontos por submissão</dt>
          <dd className="font-medium text-gray-800">{execucao.points_per_submission}</dd>
        </div>
        <div>
          <dt className="text-gray-500">Desafios criados/arquivados/reativados</dt>
          <dd className="font-medium text-gray-800">
            {execucao.challenges_created} / {execucao.challenges_archived} / {execucao.challenges_reactivated}
          </dd>
        </div>
        <div>
          <dt className="text-gray-500">Hash do snapshot</dt>
          <dd className="font-mono text-xs text-gray-700 break-all">{execucao.snapshot_hash ?? "—"}</dd>
        </div>
      </dl>

      {stateEntries.length > 0 && (
        <div>
          <p className="font-medium text-gray-700 mb-1">Tokens por estado</p>
          <ul className="space-y-0.5">
            {stateEntries.map(([key, count]) => (
              <li key={key} className="flex justify-between max-w-xs">
                <span className="text-gray-700">{key}</span>
                <span className="font-semibold">{count}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <p className="font-medium text-gray-700 mb-1">Deltas por clã</p>
        <DeltaList deltas={execucao.clan_deltas} />
      </div>

      {execucao.mass_removal_required && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 px-4 py-3 rounded-lg">
          <p className="font-medium">Remoção em massa exigida</p>
          <p>
            {execucao.mass_removal_count} token(s) —{" "}
            {execucao.mass_removal_confirmed ? "confirmada" : "não confirmada"}.
          </p>
        </div>
      )}

      {execucao.error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          <p className="font-medium mb-1">Erro</p>
          <pre className="whitespace-pre-wrap break-all text-xs">{JSON.stringify(execucao.error, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}
