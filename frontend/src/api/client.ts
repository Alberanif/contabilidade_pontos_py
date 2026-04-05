const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

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

export interface RankingEntry {
  clan: string;
  nome_completo: string;
  total_pontos: number;
  posicao: number;
}

export function fetchClans(): Promise<ClanTotal[]> {
  return request("/api/clans");
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
  limit?: number;
  offset?: number;
}): Promise<RegistrosResponse> {
  const query = new URLSearchParams();
  if (params?.clan) query.set("clan", params.clan);
  if (params?.modalidade) query.set("modalidade", params.modalidade);
  if (params?.status) query.set("status", params.status);
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
  pontos_por_clan: Record<string, number>;
  pontos_grupo_por_clan: Record<string, number>;
  pendentes_por_clan: Record<string, number>;
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
