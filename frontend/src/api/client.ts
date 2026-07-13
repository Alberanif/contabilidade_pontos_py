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
    throw new Error(error.detail || `Erro ${res.status}`);
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

export interface ExecutarResponse {
  novos_registros: number;
  novos_pendentes: number;
  pro_bono_registros: number;
  pontos_por_clan: Record<string, number>;
  pontos_grupo_por_clan: Record<string, number>;
  pendentes_por_clan: Record<string, number>;
  pontos_por_coach: Record<string, number>;
  pendentes_por_coach: Record<string, number>;
  totais_atualizados: Record<string, number>;
  mensagem: string;
}

export interface ReprocessarResponse extends ExecutarResponse {
  registros_removidos: number;
}

export interface AprovarClanResponse {
  clan: string;
  lotes_aprovados: number;
  registros_promovidos: number;
  pessoas_contabilizadas: number;
  pessoas_em_espera: number;
  pontos_adicionados: number;
  novo_total: number;
  pendentes_restantes: number;
  mensagem: string;
}

export function aprovarClan(clan: string): Promise<AprovarClanResponse> {
  return request("/api/contabilidade/aprovar-clan", {
    method: "POST",
    body: JSON.stringify({ clan }),
  });
}

export interface AprovarCoachResponse {
  coach: string;
  lotes_aprovados: number;
  registros_promovidos: number;
  pessoas_contabilizadas: number;
  pessoas_em_espera: number;
  pontos_adicionados: number;
  novo_total: number;
  pendentes_restantes: number;
  mensagem: string;
}

export function aprovarCoach(coach: string): Promise<AprovarCoachResponse> {
  return request("/api/contabilidade/aprovar-coach", {
    method: "POST",
    body: JSON.stringify({ coach }),
  });
}

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

export interface ImportarInicialResponse {
  registros_removidos: number;
  coaching_individual_importados: number;
  grupo_contabilizados: number;
  grupo_pendentes: number;
  pro_bono_importados: number;
  totais_clans: Record<string, number>;
  carry_over_por_clan: Record<string, number>;
  totais_coaches: Record<string, number>;
  carry_over_por_coach: Record<string, number>;
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

export function fetchHistorico(inicio: string, fim: string): Promise<HistoricoResponse> {
  return request(
    `/api/contabilidade/historico?inicio=${encodeURIComponent(inicio)}&fim=${encodeURIComponent(fim)}`
  );
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

// --- Desafios ---

export interface DesafioCampo {
  id: number;
  desafio_id: number;
  nome: string;
  tipo: 'texto' | 'pontuacao';
  ordem: number;
}

export interface Desafio {
  id: number;
  nome: string;
  contabilizar_pontos: boolean;
  data: string;
  campos: DesafioCampo[];
  total_registros: number;
  created_at: string;
}

export interface DesafioRegistro {
  id: number;
  desafio_id: number;
  clan: string;
  valores: Record<string, string | number>;
  total_pontos: number;
  created_at: string;
}

export function fetchDesafios(): Promise<Desafio[]> {
  return request('/api/desafios');
}

export function createDesafio(data: {
  nome: string;
  contabilizar_pontos: boolean;
  data: string;
  campos: { nome: string; tipo: string; ordem: number }[];
}): Promise<Desafio> {
  return request('/api/desafios', { method: 'POST', body: JSON.stringify(data) });
}

export function updateDesafio(
  id: number,
  data: {
    nome: string;
    contabilizar_pontos: boolean;
    data: string;
    campos: { id?: number; nome: string; tipo: string; ordem: number }[];
  }
): Promise<Desafio> {
  return request(`/api/desafios/${id}`, { method: 'PUT', body: JSON.stringify(data) });
}

export function deleteDesafio(id: number): Promise<{ mensagem: string }> {
  return request(`/api/desafios/${id}`, { method: 'DELETE' });
}

export function fetchDesafioRegistros(desafioId: number): Promise<DesafioRegistro[]> {
  return request(`/api/desafios/${desafioId}/registros`);
}

export function createDesafioRegistro(
  desafioId: number,
  data: { clan: string; valores: Record<string, string> }
): Promise<DesafioRegistro> {
  return request(`/api/desafios/${desafioId}/registros`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function deleteDesafioRegistro(
  desafioId: number,
  registroId: number
): Promise<{ mensagem: string }> {
  return request(`/api/desafios/${desafioId}/registros/${registroId}`, {
    method: 'DELETE',
  });
}

// --- Importação de Desafios via CSV ---

export interface ImportPreviewResult {
  pontos_por_clan: Record<string, number>;
  participacoes_por_clan: Record<string, number>;
  avisos: string[];
  total_linhas_contabilizadas: number;
}

export interface ImportConfig {
  nome: string;
  desafio_id?: number;
  data_inicio: string;
  data_fim: string;
  pontos_por_participacao: number;
}

export type ColumnMapping = {
  clan: string;
  nome: string;
  validado: string;
  submitted_at: string;
  token: string;
};

function buildImportFormData(file: File, mapping: ColumnMapping, config: ImportConfig): FormData {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('mapping', JSON.stringify(mapping));
  formData.append('config', JSON.stringify(config));
  return formData;
}

async function requestImport<T>(path: string, file: File, mapping: ColumnMapping, config: ImportConfig): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    body: buildImportFormData(file, mapping, config),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `Erro ${res.status}`);
  }
  return res.json();
}

export function previewImportacaoDesafio(
  file: File,
  mapping: ColumnMapping,
  config: ImportConfig
): Promise<ImportPreviewResult> {
  return requestImport('/api/desafios/importar/preview', file, mapping, config);
}

export function confirmarImportacaoDesafio(
  file: File,
  mapping: ColumnMapping,
  config: ImportConfig
): Promise<Desafio> {
  return requestImport('/api/desafios/importar/confirmar', file, mapping, config);
}

export function fetchDesafiosImportaveis(): Promise<Desafio[]> {
  return request('/api/desafios?origem=csv_import');
}
