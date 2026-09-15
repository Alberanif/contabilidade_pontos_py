// Em produção (Railway), frontend e backend rodam na mesma origem — usa string vazia.
// Em dev local, define VITE_API_BASE_URL=http://localhost:8000 no .env.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    const err = new Error(error.detail || `Erro ${res.status}`) as Error & {
      status?: number;
    };
    err.status = res.status;
    throw err;
  }
  return res.json();
}

// --- Clãs ---

export interface ClanTotal {
  id: number;
  clan: string;
  total_pontos: number;
  pessoas_em_espera: number;
  updated_at: string;
}

export interface CoachTotal {
  id: number;
  coach: string;
  total_pontos: number;
  pessoas_em_espera: number;
  updated_at: string;
}

export interface RankingEntry {
  clan: string;
  nome_completo: string;
  total_pontos: number;
  posicao: number;
}

export function fetchClans(): Promise<ClanTotal[]> {
  return request("/api/clans");
}

export function fetchCoaches(): Promise<CoachTotal[]> {
  return request("/api/coaches");
}

export function fetchRanking(): Promise<RankingEntry[]> {
  return request("/api/clans/ranking");
}

// --- Registros ---

export interface Registro {
  id: number;
  registro_hash: string;
  modalidade: string;
  clan: string;
  pontos: number;
  num_participantes: number;
  status: string;
  raw_data: string;
  processed_at: string;
  created_at: string;
}

export interface RegistrosResponse {
  registros: Registro[];
  total: number;
  limit: number;
  offset: number;
}

export function fetchRegistros(params?: {
  clan?: string;
  modalidade?: string;
  status?: string;
  status_coach?: string;
  limit?: number;
  offset?: number;
}): Promise<RegistrosResponse> {
  const query = new URLSearchParams();
  if (params?.clan) query.set("clan", params.clan);
  if (params?.modalidade) query.set("modalidade", params.modalidade);
  if (params?.status) query.set("status", params.status);
  if (params?.status_coach) query.set("status_coach", params.status_coach);
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));
  const qs = query.toString();
  return request(`/api/registros${qs ? `?${qs}` : ""}`);
}

export function deleteRegistro(id: number): Promise<{ mensagem: string; novo_total: number }> {
  return request(`/api/registros/${id}`, { method: "DELETE" });
}

// --- Contabilidade ---

// Resultado da sincronização de desafios (Google Sheets) executada como parte
// de POST /api/contabilidade/executar. Espelha `DesafioSyncResult` em
// backend/desafio_sync_service.py — os nomes/tipos dos campos devem
// permanecer idênticos aos do Pydantic model.
export interface DesafioSyncResult {
  status: string; // "success" | "failed" | "awaiting_confirmation" | "already_running"
  run_id: number | null;
  snapshot_hash: string | null;
  sheet_row_count: number;
  state_counts: Record<string, number>;
  clan_deltas: Record<string, number>;
  clan_totals_after: Record<string, number>;
  challenges_created: number;
  challenges_archived: number;
  challenges_reactivated: number;
  tokens_versioned: number;
  duration_seconds: number;
  mensagem: string;
  // Só relevantes quando status === "awaiting_confirmation".
  active_tokens_before: number | null;
  mass_removal_required: boolean;
  mass_removal_count: number;
  mass_removal_ratio: number;
}

export interface ExecutarResponse {
  novos_registros: number;
  pro_bono_registros: number;
  pontos_por_clan: Record<string, number>;
  pontos_grupo_por_clan: Record<string, number>;
  pontos_por_coach: Record<string, number>;
  totais_atualizados: Record<string, number>;
  desafios: DesafioSyncResult;
  mensagem: string;
}

// POST /api/contabilidade/reprocessar nunca chama a sincronização de
// desafios (ver backend/routers/contabilidade.py::reprocessar_contabilidade),
// então este tipo NÃO herda `desafios` de ExecutarResponse — herdar via
// `extends` faria o TypeScript mentir que todo ReprocessarResponse também tem
// esse campo.
export type ReprocessarResponse = Omit<ExecutarResponse, "desafios"> & {
  registros_removidos: number;
};

export interface ImportarResponse {
  registros_importados: number;
  registros_ja_existentes: number;
  mensagem: string;
}

export function importarContabilidade(): Promise<ImportarResponse> {
  return request("/api/contabilidade/importar", { method: "POST" });
}

export function executarContabilidade(): Promise<ExecutarResponse> {
  return request("/api/contabilidade/executar", { method: "POST" });
}

export function reprocessarContabilidade(): Promise<ReprocessarResponse> {
  return request("/api/contabilidade/reprocessar", { method: "POST" });
}

// Confirma (ou recusa) a aplicação de um plano de sincronização de desafios
// que retornou status "awaiting_confirmation" por exigir remoção em massa
// (RF-17). O backend só precisa do `snapshot_hash` da prévia — não existe
// `run_id` de entrada; se a planilha/estado mudou nesse meio-tempo, o backend
// rejeita o hash obsoleto e devolve um DesafioSyncResult "failed" refletindo
// a realidade atual (nunca aplica o plano antigo por engano).
export function confirmarDesafios(
  snapshotHash: string,
  confirmarRemocaoEmMassa: boolean
): Promise<DesafioSyncResult> {
  return request("/api/contabilidade/confirmar-desafios", {
    method: "POST",
    body: JSON.stringify({
      snapshot_hash: snapshotHash,
      confirmar_remocao_em_massa: confirmarRemocaoEmMassa,
    }),
  });
}

export interface ImportarInicialResponse {
  registros_removidos: number;
  coaching_individual_importados: number;
  grupo_contabilizados: number;
  pro_bono_importados: number;
  totais_clans: Record<string, number>;
  totais_coaches: Record<string, number>;
  mensagem: string;
}

export function importarInicial(): Promise<ImportarInicialResponse> {
  return request("/api/contabilidade/importar-inicial", { method: "POST" });
}

export interface AtualizarPlanilhaResponse {
  totais_atualizados: Record<string, number>;
  mensagem: string;
}

export function atualizarPlanilha(): Promise<AtualizarPlanilhaResponse> {
  return request("/api/contabilidade/atualizar-planilha", { method: "POST" });
}

// --- Histórico ---

export interface HistoricoResponse {
  clans: Record<string, number>;
  coaches: Record<string, number>;
}

export function fetchHistorico(inicio: string, fim?: string): Promise<HistoricoResponse> {
  const params = new URLSearchParams({ inicio });
  if (fim) params.set("fim", fim);
  return request(`/api/contabilidade/historico?${params}`);
}

export function fetchTotaisPorTipo(
  tipo: "pagante" | "pro_bono" | "desafios",
  inicio?: string,
  fim?: string
): Promise<HistoricoResponse> {
  const params = new URLSearchParams({ tipo });
  if (inicio) params.set("inicio", inicio);
  if (fim) params.set("fim", fim);
  return request(`/api/contabilidade/totais-por-tipo?${params}`);
}

// --- Desafios: auditoria somente leitura ---
//
// A tela de Desafios (frontend/src/pages/Desafios.tsx) é uma consulta/auditoria
// somente leitura sobre os dados sincronizados da Google Sheet — não existe
// mais nenhuma escrita de desafio pelo frontend (criar/editar/excluir desafio
// ou registro, e o antigo assistente de importação via CSV foram removidos;
// todo endpoint mutável equivalente no backend responde 410). Os tipos e
// funções abaixo espelham os Pydantic models de
// `backend/routers/desafio_auditoria.py` — nomes/tipos devem permanecer
// idênticos aos de lá.

export interface DesafioAuditoria {
  id: number;
  nome: string;
  contabilizar_pontos: boolean;
  data: string | null;
  data_inicio: string | null;
  data_fim: string | null;
  prazo_apuracao: string | null;
  apurado_em: string | null;
  origem: string;
  nome_normalizado: string | null;
  status: string; // "ativo" | "arquivado" (valor bruto do banco)
  arquivado_at: string | null;
  reativado_at: string | null;
  updated_at: string;
  created_at: string;
}

export interface DesafioAuditoriaDetalhe extends DesafioAuditoria {
  pontos_por_clan: Record<string, number>;
  pontos_por_coach: Record<string, number>;
}

// As 9 células brutas da planilha (colunas A-I), tanto na forma posicional
// (`raw_cells`) quanto nomeada (`raw_clan_legacy` ... `raw_token`, na mesma
// ordem das colunas).
export interface DesafioSubmissao {
  token: string;
  row_numbers: number[];
  raw_cells: unknown[];
  raw_clan_legacy: string | null;
  raw_name: string | null;
  coach: string | null;
  raw_validation: string | null;
  raw_link: string | null;
  raw_observation: string | null;
  raw_challenge: string | null;
  raw_clan_current: string | null;
  raw_submitted_at: string | null;
  raw_token: string | null;
  clan: string | null;
  challenge_normalized: string | null;
  desafio_id: number | null;
  submitted_at: string | null;
  status: string; // "active_counted" | "active_not_counted" | "invalid" | "conflicted" | "inactive_missing" | "blocked_by_guardrail"
  revisao_status?: "pendente" | "aprovado" | "reprovado";
  revisado_por?: string | null;
  revisado_em?: string | null;
  invalid_reasons: string[];
  points: number;
  content_hash: string;
  first_seen_run_id: number;
  last_seen_run_id: number;
  inactivated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface DesafioSubmissaoVersao {
  id: number;
  token: string;
  sync_run_id: number;
  version_number: number;
  row_numbers: number[];
  raw_cells: unknown[];
  raw_clan_legacy: string | null;
  raw_name: string | null;
  coach: string | null;
  raw_validation: string | null;
  raw_link: string | null;
  raw_observation: string | null;
  raw_challenge: string | null;
  raw_clan_current: string | null;
  raw_submitted_at: string | null;
  raw_token: string | null;
  previous_state: Record<string, unknown> | null;
  current_state: Record<string, unknown>;
  previous_status: string | null;
  current_status: string;
  point_delta: number;
  clan_deltas: Record<string, number>;
  change_reason: string;
  observed_at: string;
}

export interface DesafioSincronizacao {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: string; // "running" | "succeeded" | "failed" | "awaiting_confirmation" | "cancelled"
  snapshot_hash: string | null;
  sheet_row_count: number;
  state_counts: Record<string, number>;
  clan_deltas: Record<string, number>;
  challenges_created: number;
  challenges_archived: number;
  challenges_reactivated: number;
  points_per_submission: number;
  mass_removal_required: boolean;
  mass_removal_confirmed: boolean;
  mass_removal_count: number;
  error: Record<string, unknown> | null;
  created_at: string;
}

export function fetchDesafiosAuditoria(
  status: "active" | "archived" | "all" = "all"
): Promise<DesafioAuditoria[]> {
  return request(`/api/desafios?status=${status}`);
}

export function fetchDesafioAuditoria(id: number): Promise<DesafioAuditoriaDetalhe> {
  return request(`/api/desafios/${id}`);
}

export function fetchSubmissoesDoDesafio(
  id: number,
  params?: { clan?: string; status?: string; limit?: number; offset?: number }
): Promise<DesafioSubmissao[]> {
  const query = new URLSearchParams();
  if (params?.clan) query.set("clan", params.clan);
  if (params?.status) query.set("status", params.status);
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));
  const qs = query.toString();
  return request(`/api/desafios/${id}/submissoes${qs ? `?${qs}` : ""}`);
}

export function fetchSubmissaoPorToken(token: string): Promise<DesafioSubmissao> {
  return request(`/api/desafios/submissoes/${encodeURIComponent(token)}`);
}

export function fetchVersoesDaSubmissao(token: string): Promise<DesafioSubmissaoVersao[]> {
  return request(`/api/desafios/submissoes/${encodeURIComponent(token)}/versoes`);
}

export function fetchSincronizacoes(limit = 50, offset = 0): Promise<DesafioSincronizacao[]> {
  return request(`/api/desafios/sincronizacoes?limit=${limit}&offset=${offset}`);
}

export function fetchSincronizacao(runId: number): Promise<DesafioSincronizacao> {
  return request(`/api/desafios/sincronizacoes/${runId}`);
}

// --- Aliases de Coaches (IA / Groq) ---

export interface PendingAlias {
  id: number;
  alias_raw: string;
  coach_sugerido: string;
  confianca: number;
  origem: string;
  status: string;
  created_at: string;
}

export interface SugerirAliasesResponse {
  total_analisados: number;
  auto_aprovados: number;
  enviados_para_fila: number;
  sem_correspondencia: number;
  mensagem: string;
}

export function fetchPendingAliases(status = "pendente"): Promise<PendingAlias[]> {
  return request(`/api/contabilidade/aliases-pendentes?status=${status}`);
}

export function triggerSugerirAliasesLLM(): Promise<SugerirAliasesResponse> {
  return request("/api/contabilidade/sugerir-aliases-llm", { method: "POST" });
}

export function aprovarAliasPendente(
  id_pendente: number,
  coach_canonico_override?: string
): Promise<{ status: string; mensagem: string }> {
  return request("/api/contabilidade/aprovar-alias-pendente", {
    method: "POST",
    body: JSON.stringify({ id_pendente, coach_canonico_override }),
  });
}

export function rejeitarAliasPendente(id_pendente: number): Promise<{ status: string; mensagem: string }> {
  return request("/api/contabilidade/rejeitar-alias-pendente", {
    method: "POST",
    body: JSON.stringify({ id_pendente }),
  });
}

// --- Coaches por Clã ---
//
// Atribuição fixa de cada coach a um único clã (RF da PRD #28). Espelha o
// Pydantic model de `backend/routers/coach_clas.py` — nomes/tipos devem
// permanecer idênticos aos de lá. `createCoachCla` responde 409 quando o
// coach já pertence a outro clã; o chamador distingue esse caso pela
// propriedade `status` no erro lançado (ver `request()` acima).

export interface CoachCla {
  coach_canonico: string;
  clan: string;
  categoria: string;
}

export function fetchCoachClas(clan?: string): Promise<CoachCla[]> {
  return request(`/api/coach-clas${clan ? `?clan=${encodeURIComponent(clan)}` : ""}`);
}

export function createCoachCla(payload: {
  coach: string;
  clan: string;
  categoria: string;
}): Promise<CoachCla> {
  return request("/api/coach-clas", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateCoachCla(
  coachCanonico: string,
  payload: { clan?: string; categoria?: string }
): Promise<CoachCla> {
  return request(`/api/coach-clas/${encodeURIComponent(coachCanonico)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteCoachCla(coachCanonico: string): Promise<void> {
  return request(`/api/coach-clas/${encodeURIComponent(coachCanonico)}`, {
    method: "DELETE",
  });
}

// --- Desafios: Apuração por Percentual e Prazo ---

export interface ClanApuracaoEntry {
  clan: string;
  participantes: number;
  total_grupo: number;
  percentual: number;
  pontos: number;
}

export interface DesafioApuracaoResponse {
  desafio_id: number;
  prazo_apuracao: string | null;
  apurado_em: string | null;
  provisorio: boolean;
  clas: ClanApuracaoEntry[];
}

export function setDesafioPrazo(desafioId: number, prazo: string | null): Promise<DesafioAuditoria> {
  return request(`/api/desafios/${desafioId}/prazo`, {
    method: "PATCH",
    body: JSON.stringify({ prazo_apuracao: prazo }),
  });
}

export function getDesafioApuracao(desafioId: number): Promise<DesafioApuracaoResponse> {
  return request(`/api/desafios/${desafioId}/apuracao`);
}

export function revisarSubmissao(
  token: string,
  status: "aprovado" | "reprovado" | "pendente"
): Promise<{ token: string; status: string }> {
  return request(`/api/desafios/submissoes/${token}/revisar`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });
}

