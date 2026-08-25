import type { DesafioSubmissao } from "../api/client";

// Rótulos em pt-BR para o vocabulário de status de submissão retornado por
// `GET /api/desafios/{id}/submissoes` e `GET /api/desafios/submissoes/{token}`
// (ver backend/routers/desafio_auditoria.py::DesafioSubmissionResponse).
// Mantido privado a este arquivo (não exportado) para não violar a regra de
// fast-refresh do eslint, que exige que um arquivo de componente só exporte
// componentes — `Desafios.tsx` mantém sua própria cópia deste mapa (mesmo
// padrão de `ExecutionResult.tsx`/`STATE_LABELS`, que também não é
// compartilhado entre arquivos).
const SUBMISSION_STATUS_LABELS: Record<string, string> = {
  active_counted: "Ativo contabilizado",
  active_not_counted: "Ativo não contabilizado",
  invalid: "Inválido",
  conflicted: "Conflitante",
  inactive_missing: "Inativo (ausente)",
  blocked_by_guardrail: "Bloqueado por guardrail",
};

// As 9 células brutas da planilha (colunas A-I), na mesma ordem em que
// aparecem na planilha e em `raw_cells` — ver o comentário de
// `DesafioSubmissionResponse` no backend.
const RAW_FIELDS: { key: keyof DesafioSubmissao; label: string; coluna: string }[] = [
  { key: "raw_clan_legacy", label: "Clã (legado)", coluna: "A" },
  { key: "raw_name", label: "Nome", coluna: "B" },
  { key: "raw_validation", label: "Validação", coluna: "C" },
  { key: "raw_link", label: "Link", coluna: "D" },
  { key: "raw_observation", label: "Observação", coluna: "E" },
  { key: "raw_challenge", label: "Desafio", coluna: "F" },
  { key: "raw_clan_current", label: "Clã (atual)", coluna: "G" },
  { key: "raw_submitted_at", label: "Enviado em", coluna: "H" },
  { key: "raw_token", label: "Token", coluna: "I" },
];

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("pt-BR");
}

export interface SubmissionDetailProps {
  submissao: DesafioSubmissao;
  onShowVersions?: () => void;
  onOpenSyncRun?: (runId: number) => void;
}

/**
 * Detalhe somente leitura de um token de submissão: estado atual, motivos de
 * invalidação e as 9 células brutas da planilha (colunas A-I), na ordem em
 * que aparecem nela.
 */
export default function SubmissionDetail({ submissao, onShowVersions, onOpenSyncRun }: SubmissionDetailProps) {
  return (
    <div className="space-y-6" data-testid="submission-detail">
      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <p className="text-xs text-gray-500">Token</p>
            <p className="font-mono text-sm text-gray-800 break-all">{submissao.token}</p>
          </div>
          <span className="px-2 py-0.5 rounded text-xs font-medium bg-indigo-100 text-indigo-700 whitespace-nowrap">
            {SUBMISSION_STATUS_LABELS[submissao.status] ?? submissao.status}
          </span>
        </div>

        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm" data-testid="current-state">
          <div>
            <dt className="text-gray-500">Clã</dt>
            <dd className="font-medium text-gray-800">{submissao.clan ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Desafio</dt>
            <dd className="font-medium text-gray-800">{submissao.challenge_normalized ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Pontos</dt>
            <dd className="font-medium text-gray-800">{submissao.points}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Enviado em</dt>
            <dd className="font-medium text-gray-800">{formatDateTime(submissao.submitted_at)}</dd>
          </div>
        </dl>

        {submissao.invalid_reasons.length > 0 && (
          <div>
            <p className="text-sm font-semibold text-red-700 mb-1">Motivos de invalidação</p>
            <ul className="list-disc list-inside text-sm text-red-700 space-y-0.5">
              {submissao.invalid_reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
          <button
            type="button"
            onClick={() => onOpenSyncRun?.(submissao.first_seen_run_id)}
            className="text-indigo-600 hover:underline"
          >
            Primeira vez visto na execução #{submissao.first_seen_run_id}
          </button>
          <button
            type="button"
            onClick={() => onOpenSyncRun?.(submissao.last_seen_run_id)}
            className="text-indigo-600 hover:underline"
          >
            Última vez visto na execução #{submissao.last_seen_run_id}
          </button>
        </div>

        {onShowVersions && (
          <button
            type="button"
            onClick={onShowVersions}
            className="text-indigo-600 hover:text-indigo-800 text-sm font-medium"
          >
            Ver histórico de versões →
          </button>
        )}
      </div>

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full text-sm" data-testid="raw-fields-table">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200 text-left text-gray-500">
              <th className="py-2 px-4 font-medium w-10">Col.</th>
              <th className="py-2 px-4 font-medium">Campo</th>
              <th className="py-2 px-4 font-medium">Valor bruto</th>
            </tr>
          </thead>
          <tbody>
            {RAW_FIELDS.map((f) => (
              <tr key={f.key} className="border-b border-gray-100">
                <td className="py-2 px-4 text-gray-400">{f.coluna}</td>
                <td className="py-2 px-4 text-gray-600">{f.label}</td>
                <td className="py-2 px-4 text-gray-800 break-all">
                  {submissao[f.key] === null || submissao[f.key] === undefined
                    ? "—"
                    : String(submissao[f.key])}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
