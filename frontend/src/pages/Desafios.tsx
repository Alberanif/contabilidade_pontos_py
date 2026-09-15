import { useEffect, useState } from "react";
import {
  fetchDesafiosAuditoria,
  fetchDesafioAuditoria,
  fetchSubmissoesDoDesafio,
  fetchSubmissaoPorToken,
  fetchVersoesDaSubmissao,
  fetchSincronizacoes,
  fetchSincronizacao,
  getDesafioApuracao,
  revisarSubmissao,
  type DesafioAuditoria,
  type DesafioAuditoriaDetalhe,
  type DesafioSubmissao,
  type DesafioSubmissaoVersao,
  type DesafioSincronizacao,
  type DesafioApuracaoResponse,
} from "../api/client";
import DesafioFilters, { type DesafioFiltersValue } from "../components/DesafioFilters";
import SubmissionDetail from "../components/SubmissionDetail";
import SyncRunDetail from "../components/SyncRunDetail";
import { DesafioPrazoEditor } from "../components/DesafioPrazoEditor";
import { DesafioClanApuracaoTable } from "../components/DesafioClanApuracaoTable";

// Tela de consulta e auditoria de Desafios (issue #21) — somente leitura,
// contra a API de auditoria da Task 7 (backend/routers/desafio_auditoria.py).
// Não existe mais nenhuma criação/edição/exclusão de desafio ou registro, nem
// o assistente de importação via CSV: todo endpoint mutável equivalente no
// backend responde 410 (issue #17).

// Rótulos em pt-BR para o vocabulário de status de submissão — mesma lista de
// `SubmissionDetail.tsx` (não compartilhada por arquivo, ver comentário lá).
const SUBMISSION_STATUS_LABELS: Record<string, string> = {
  active_counted: "Ativo contabilizado",
  active_not_counted: "Ativo não contabilizado",
  invalid: "Inválido",
  conflicted: "Conflitante",
  inactive_missing: "Inativo (ausente)",
  blocked_by_guardrail: "Bloqueado por guardrail",
};

const SUBMISSION_STATUS_OPTIONS = Object.entries(SUBMISSION_STATUS_LABELS).map(([value, label]) => ({
  value,
  label,
}));

const DESAFIO_STATUS_LABELS: Record<string, string> = {
  ativo: "Ativo",
  arquivado: "Arquivado",
};

// Limite explícito de submissões buscadas por página — casa com o default
// implícito do backend (limit=100). Como não há controle de paginação nesta
// tela (fora de escopo), quando a contagem retornada bate exatamente nesse
// limite exibimos um aviso: pode haver mais linhas que a UI não está
// mostrando, e o filtro de período client-side só enxerga esta página.
const SUBMISSOES_LIMIT = 100;

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "-";
  const parts = dateStr.substring(0, 10).split("-");
  if (parts.length !== 3) return dateStr;
  const [year, month, day] = parts;
  return `${day}/${month}/${year}`;
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("pt-BR");
}

function formatPeriodo(d: DesafioAuditoria): string {
  if (d.data_inicio && d.data_fim) {
    return `${formatDate(d.data_inicio)} - ${formatDate(d.data_fim)}`;
  }
  return formatDate(d.data);
}

function ClanDeltaList({ deltas }: { deltas: Record<string, number> }) {
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

type DesafioView =
  | { name: "lista" }
  | { name: "detalhe"; id: number }
  | { name: "submissao"; token: string }
  | { name: "versoes"; token: string };

type SyncView = { name: "lista" } | { name: "detalhe"; runId: number };

const tabClass = (active: boolean) =>
  `whitespace-nowrap py-3 px-1 border-b-2 font-medium text-sm ${
    active
      ? "border-indigo-500 text-indigo-600"
      : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
  }`;

const toggleClass = (active: boolean) =>
  `px-3 py-1.5 text-sm font-medium transition-colors ${
    active ? "bg-indigo-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50"
  }`;

export default function Desafios() {
  const [aba, setAba] = useState<"desafios" | "sincronizacoes">("desafios");

  // --- Aba Desafios ---
  const [desafioView, setDesafioView] = useState<DesafioView>({ name: "lista" });

  const [statusFiltroDesafio, setStatusFiltroDesafio] = useState<"active" | "archived" | "all">("active");
  const [desafios, setDesafios] = useState<DesafioAuditoria[]>([]);
  const [loadingDesafios, setLoadingDesafios] = useState(true);
  const [erroDesafios, setErroDesafios] = useState("");

  const [desafioDetalhe, setDesafioDetalhe] = useState<DesafioAuditoriaDetalhe | null>(null);
  const [loadingDetalhe, setLoadingDetalhe] = useState(false);
  const [erroDetalhe, setErroDetalhe] = useState("");

  const [filtros, setFiltros] = useState<DesafioFiltersValue>({
    clan: "",
    status: "",
    dataInicio: "",
    dataFim: "",
  });
  const [submissoes, setSubmissoes] = useState<DesafioSubmissao[]>([]);
  const [loadingSubmissoes, setLoadingSubmissoes] = useState(false);
  const [erroSubmissoes, setErroSubmissoes] = useState("");
  const [paginaSubmissoes, setPaginaSubmissoes] = useState(1);

  const [submissaoAtual, setSubmissaoAtual] = useState<DesafioSubmissao | null>(null);
  const [loadingSubmissao, setLoadingSubmissao] = useState(false);
  const [erroSubmissao, setErroSubmissao] = useState("");

  const [versoes, setVersoes] = useState<DesafioSubmissaoVersao[]>([]);
  const [loadingVersoes, setLoadingVersoes] = useState(false);
  const [erroVersoes, setErroVersoes] = useState("");

  // --- Aba Sincronizações ---
  const [syncView, setSyncView] = useState<SyncView>({ name: "lista" });
  const [execucoes, setExecucoes] = useState<DesafioSincronizacao[]>([]);
  const [loadingExecucoes, setLoadingExecucoes] = useState(true);
  const [erroExecucoes, setErroExecucoes] = useState("");

  const [execucaoAtual, setExecucaoAtual] = useState<DesafioSincronizacao | null>(null);
  const [loadingExecucao, setLoadingExecucao] = useState(false);
  const [erroExecucao, setErroExecucao] = useState("");

  // --- Busca de token (lookup direto, não é filtro de lista) ---
  const [tokenBusca, setTokenBusca] = useState("");
  const [buscandoToken, setBuscandoToken] = useState(false);
  const [erroBuscaToken, setErroBuscaToken] = useState("");

  // --- Efeitos de carregamento ---

  useEffect(() => {
    let cancelado = false;
    setLoadingDesafios(true);
    setErroDesafios("");
    fetchDesafiosAuditoria(statusFiltroDesafio)
      .then((data) => {
        if (!cancelado) setDesafios(data);
      })
      .catch((e) => {
        if (!cancelado) setErroDesafios(e instanceof Error ? e.message : "Erro ao carregar desafios");
      })
      .finally(() => {
        if (!cancelado) setLoadingDesafios(false);
      });
    return () => {
      cancelado = true;
    };
  }, [statusFiltroDesafio]);

  const desafioDetalheId = desafioView.name === "detalhe" ? desafioView.id : null;

  useEffect(() => {
    if (desafioDetalheId == null) return;
    let cancelado = false;
    setLoadingDetalhe(true);
    setErroDetalhe("");
    setDesafioDetalhe(null);
    fetchDesafioAuditoria(desafioDetalheId)
      .then((data) => {
        if (!cancelado) setDesafioDetalhe(data);
      })
      .catch((e) => {
        if (!cancelado) setErroDetalhe(e instanceof Error ? e.message : "Erro ao carregar desafio");
      })
      .finally(() => {
        if (!cancelado) setLoadingDetalhe(false);
      });
    return () => {
      cancelado = true;
    };
  }, [desafioDetalheId]);

  const [apuracao, setApuracao] = useState<DesafioApuracaoResponse | null>(null);
  const [loadingApuracao, setLoadingApuracao] = useState(false);

  const carregarApuracao = (id: number) => {
    setLoadingApuracao(true);
    getDesafioApuracao(id)
      .then((data) => setApuracao(data))
      .catch((e) => console.error("Erro ao carregar apuração", e))
      .finally(() => setLoadingApuracao(false));
  };

  const carregarSubmissoes = (id: number) => {
    setLoadingSubmissoes(true);
    fetchSubmissoesDoDesafio(id, {
      clan: filtros.clan || undefined,
      status: filtros.status || undefined,
      limit: SUBMISSOES_LIMIT,
    })
      .then((data) => setSubmissoes(data))
      .catch((e) => setErroSubmissoes(e instanceof Error ? e.message : "Erro ao carregar submissões"))
      .finally(() => setLoadingSubmissoes(false));
  };

  useEffect(() => {
    if (desafioDetalheId == null) return;
    carregarApuracao(desafioDetalheId);
  }, [desafioDetalheId]);

  const handleToggleReprovacao = async (token: string, reprovarAgora: boolean) => {
    try {
      await revisarSubmissao(token, reprovarAgora ? "reprovado" : "pendente");
      if (desafioDetalheId) {
        carregarSubmissoes(desafioDetalheId);
        carregarApuracao(desafioDetalheId);
      }
    } catch (err) {
      alert(`Erro ao revisar submissão: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  useEffect(() => {
    if (desafioDetalheId == null) return;
    let cancelado = false;
    setLoadingSubmissoes(true);
    setErroSubmissoes("");
    setSubmissoes([]);
    setPaginaSubmissoes(1);
    fetchSubmissoesDoDesafio(desafioDetalheId, {
      clan: filtros.clan || undefined,
      status: filtros.status || undefined,
      limit: SUBMISSOES_LIMIT,
    })
      .then((data) => {
        if (!cancelado) setSubmissoes(data);
      })
      .catch((e) => {
        if (!cancelado) setErroSubmissoes(e instanceof Error ? e.message : "Erro ao carregar submissões");
      })
      .finally(() => {
        if (!cancelado) setLoadingSubmissoes(false);
      });
    return () => {
      cancelado = true;
    };
  }, [desafioDetalheId, filtros.clan, filtros.status]);

  const submissaoToken = desafioView.name === "submissao" ? desafioView.token : null;

  useEffect(() => {
    if (submissaoToken == null) return;
    let cancelado = false;
    setLoadingSubmissao(true);
    setErroSubmissao("");
    setSubmissaoAtual(null);
    fetchSubmissaoPorToken(submissaoToken)
      .then((data) => {
        if (!cancelado) setSubmissaoAtual(data);
      })
      .catch((e) => {
        if (!cancelado) setErroSubmissao(e instanceof Error ? e.message : "Erro ao carregar submissão");
      })
      .finally(() => {
        if (!cancelado) setLoadingSubmissao(false);
      });
    return () => {
      cancelado = true;
    };
  }, [submissaoToken]);

  const versoesToken = desafioView.name === "versoes" ? desafioView.token : null;

  useEffect(() => {
    if (versoesToken == null) return;
    let cancelado = false;
    setLoadingVersoes(true);
    setErroVersoes("");
    setVersoes([]);
    fetchVersoesDaSubmissao(versoesToken)
      .then((data) => {
        if (!cancelado) setVersoes(data);
      })
      .catch((e) => {
        if (!cancelado) setErroVersoes(e instanceof Error ? e.message : "Erro ao carregar histórico de versões");
      })
      .finally(() => {
        if (!cancelado) setLoadingVersoes(false);
      });
    return () => {
      cancelado = true;
    };
  }, [versoesToken]);

  useEffect(() => {
    if (aba !== "sincronizacoes" || syncView.name !== "lista") return;
    let cancelado = false;
    setLoadingExecucoes(true);
    setErroExecucoes("");
    fetchSincronizacoes()
      .then((data) => {
        if (!cancelado) setExecucoes(data);
      })
      .catch((e) => {
        if (!cancelado) setErroExecucoes(e instanceof Error ? e.message : "Erro ao carregar sincronizações");
      })
      .finally(() => {
        if (!cancelado) setLoadingExecucoes(false);
      });
    return () => {
      cancelado = true;
    };
  }, [aba, syncView.name]);

  const execucaoRunId = syncView.name === "detalhe" ? syncView.runId : null;

  useEffect(() => {
    if (execucaoRunId == null) return;
    let cancelado = false;
    setLoadingExecucao(true);
    setErroExecucao("");
    setExecucaoAtual(null);
    fetchSincronizacao(execucaoRunId)
      .then((data) => {
        if (!cancelado) setExecucaoAtual(data);
      })
      .catch((e) => {
        if (!cancelado) setErroExecucao(e instanceof Error ? e.message : "Erro ao carregar execução");
      })
      .finally(() => {
        if (!cancelado) setLoadingExecucao(false);
      });
    return () => {
      cancelado = true;
    };
  }, [execucaoRunId]);

  // --- Ações de navegação ---

  const abrirDesafio = (id: number) => {
    setFiltros({ clan: "", status: "", dataInicio: "", dataFim: "" });
    setPaginaSubmissoes(1);
    setDesafioView({ name: "detalhe", id });
  };

  const abrirSubmissao = (token: string) => {
    setDesafioView({ name: "submissao", token });
  };

  const abrirVersoes = (token: string) => {
    setDesafioView({ name: "versoes", token });
  };

  const abrirExecucao = (runId: number) => {
    setAba("sincronizacoes");
    setSyncView({ name: "detalhe", runId });
  };

  const handleBuscarToken = async () => {
    const token = tokenBusca.trim();
    if (!token) return;
    try {
      setBuscandoToken(true);
      setErroBuscaToken("");
      const submissao = await fetchSubmissaoPorToken(token);
      setSubmissaoAtual(submissao);
      setAba("desafios");
      setDesafioView({ name: "submissao", token: submissao.token });
    } catch (e) {
      setErroBuscaToken(e instanceof Error ? e.message : "Token não encontrado");
    } finally {
      setBuscandoToken(false);
    }
  };

  const TAMANHO_PAGINA_SUBMISSOES = 10;

  const submissoesFiltradas = submissoes.filter((s) => {
    if (!filtros.dataInicio && !filtros.dataFim) return true;
    if (!s.submitted_at) return false;
    const dia = s.submitted_at.slice(0, 10);
    if (filtros.dataInicio && dia < filtros.dataInicio) return false;
    if (filtros.dataFim && dia > filtros.dataFim) return false;
    return true;
  });

  const totalPaginasSubmissoes = Math.ceil(submissoesFiltradas.length / TAMANHO_PAGINA_SUBMISSOES) || 1;
  const submissoesPaginadas = submissoesFiltradas.slice(
    (paginaSubmissoes - 1) * TAMANHO_PAGINA_SUBMISSOES,
    paginaSubmissoes * TAMANHO_PAGINA_SUBMISSOES
  );

  // --- Elementos compartilhados ---

  const tokenSearchBox = (
    <div className="flex items-end gap-2">
      <div>
        <label htmlFor="busca-token" className="block text-xs font-medium text-gray-500 mb-1">
          Token
        </label>
        <input
          id="busca-token"
          type="text"
          value={tokenBusca}
          onChange={(e) => setTokenBusca(e.target.value)}
          placeholder="Buscar por token exato"
          className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-56 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>
      <button
        type="button"
        onClick={handleBuscarToken}
        disabled={buscandoToken}
        className="bg-indigo-600 text-white px-4 py-1.5 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {buscandoToken ? "Buscando..." : "Buscar"}
      </button>
    </div>
  );

  // --- Aba Desafios ---

  let conteudoDesafios: React.ReactNode;

  if (desafioView.name === "lista") {
    conteudoDesafios = (
      <div className="space-y-4">
        <div className="flex rounded-lg border border-gray-300 overflow-hidden w-fit">
          <button
            type="button"
            onClick={() => setStatusFiltroDesafio("active")}
            className={toggleClass(statusFiltroDesafio === "active")}
          >
            Ativos
          </button>
          <button
            type="button"
            onClick={() => setStatusFiltroDesafio("archived")}
            className={`${toggleClass(statusFiltroDesafio === "archived")} border-l border-gray-300`}
          >
            Arquivados
          </button>
          <button
            type="button"
            onClick={() => setStatusFiltroDesafio("all")}
            className={`${toggleClass(statusFiltroDesafio === "all")} border-l border-gray-300`}
          >
            Todos
          </button>
        </div>

        {erroDesafios && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">{erroDesafios}</div>
        )}

        {loadingDesafios ? (
          <p className="text-gray-500">Carregando desafios...</p>
        ) : desafios.length === 0 ? (
          <p className="text-gray-500">Nenhum desafio encontrado.</p>
        ) : (
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200 text-left text-gray-500">
                  <th className="py-3 px-4 font-medium">Nome</th>
                  <th className="py-3 px-4 font-medium">Período</th>
                  <th className="py-3 px-4 font-medium">Status</th>
                  <th className="py-3 px-4 font-medium text-center">Pontuação</th>
                  <th className="py-3 px-4 font-medium">Origem</th>
                </tr>
              </thead>
              <tbody>
                {desafios.map((d) => (
                  <tr key={d.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="py-3 px-4">
                      <button
                        onClick={() => abrirDesafio(d.id)}
                        className="font-medium text-indigo-600 hover:underline text-left"
                      >
                        {d.nome}
                      </button>
                    </td>
                    <td className="py-3 px-4 text-gray-600">{formatPeriodo(d)}</td>
                    <td className="py-3 px-4">
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-medium ${
                          d.status === "ativo" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {DESAFIO_STATUS_LABELS[d.status] ?? d.status}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-medium ${
                          d.contabilizar_pontos ? "bg-indigo-100 text-indigo-700" : "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {d.contabilizar_pontos ? "Contabiliza" : "Não contabiliza"}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-gray-600">{d.origem}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  } else if (desafioView.name === "detalhe") {
    conteudoDesafios = (
      <div className="space-y-6">
        <button onClick={() => setDesafioView({ name: "lista" })} className="text-gray-500 hover:text-gray-700 text-sm">
          ← Desafios
        </button>

        {erroDetalhe && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">{erroDetalhe}</div>
        )}

        {loadingDetalhe ? (
          <p className="text-gray-500">Carregando desafio...</p>
        ) : desafioDetalhe ? (
          <>
            <div className="flex items-center gap-3 flex-wrap">
              <h3 className="text-xl font-bold text-gray-800">{desafioDetalhe.nome}</h3>
              <span
                className={`px-2 py-0.5 rounded text-xs font-medium ${
                  desafioDetalhe.status === "ativo" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-600"
                }`}
              >
                {DESAFIO_STATUS_LABELS[desafioDetalhe.status] ?? desafioDetalhe.status}
              </span>
              <span className="text-sm text-gray-500">{formatPeriodo(desafioDetalhe)}</span>
            </div>

            <DesafioPrazoEditor
              desafioId={desafioDetalhe.id}
              prazoAtual={desafioDetalhe.prazo_apuracao}
              apuradoEm={desafioDetalhe.apurado_em}
              onUpdate={() => {
                fetchDesafioAuditoria(desafioDetalhe.id).then((d) => setDesafioDetalhe(d));
                carregarApuracao(desafioDetalhe.id);
              }}
            />

            <DesafioClanApuracaoTable apuracao={apuracao} loading={loadingApuracao} />

            <DesafioFilters
              value={filtros}
              onChange={(f) => {
                setFiltros(f);
                setPaginaSubmissoes(1);
              }}
              statusOptions={SUBMISSION_STATUS_OPTIONS}
            />

            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-2">
                Submissões ({submissoesFiltradas.length})
              </h4>

              {submissoes.length === SUBMISSOES_LIMIT && (
                <p className="text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-xs mb-2">
                  Mostrando as primeiras {SUBMISSOES_LIMIT} submissões; o filtro de período se aplica apenas a esta
                  página.
                </p>
              )}

              {erroSubmissoes && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-2">
                  {erroSubmissoes}
                </div>
              )}

              {loadingSubmissoes ? (
                <p className="text-gray-500 text-sm">Carregando submissões...</p>
              ) : submissoesFiltradas.length === 0 ? (
                <p className="text-gray-500 text-sm">Nenhuma submissão encontrada para os filtros atuais.</p>
              ) : (
                <>
                  <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-gray-50 border-b border-gray-200 text-left text-gray-500">
                          <th className="py-2 px-4 font-medium">Token</th>
                          <th className="py-2 px-4 font-medium">Clã</th>
                          <th className="py-2 px-4 font-medium">Coach</th>
                          <th className="py-2 px-4 font-medium">Status Reconciliação</th>
                          <th className="py-2 px-4 font-medium text-center">Revisão Manual</th>
                          <th className="py-2 px-4 font-medium text-right">Pontos</th>
                          <th className="py-2 px-4 font-medium">Enviado em</th>
                        </tr>
                      </thead>
                      <tbody>
                        {submissoesPaginadas.map((s) => {
                          const isPostCorte = Boolean(
                            s.submitted_at && s.submitted_at >= "2026-08-01"
                          );
                          const revStatus = s.revisao_status || "pendente";

                          return (
                            <tr key={s.token} className="border-b border-gray-100 hover:bg-gray-50">
                              <td className="py-2 px-4">
                                <button
                                  onClick={() => abrirSubmissao(s.token)}
                                  className="font-mono text-indigo-600 hover:underline text-left"
                                >
                                  {s.token}
                                </button>
                              </td>
                              <td className="py-2 px-4 text-gray-700">{s.clan ?? "—"}</td>
                              <td className="py-2 px-4 text-gray-700">{s.coach ?? "—"}</td>
                              <td className="py-2 px-4 text-gray-700">
                                {SUBMISSION_STATUS_LABELS[s.status] ?? s.status}
                              </td>
                              <td className="py-2 px-4 text-center">
                                {isPostCorte ? (
                                  <div className="flex items-center justify-center gap-1.5">
                                    <span
                                      className={`px-2 py-0.5 rounded text-xs font-semibold ${
                                        revStatus === "reprovado"
                                          ? "bg-red-100 text-red-700"
                                          : "bg-green-100 text-green-700"
                                      }`}
                                    >
                                      {revStatus === "reprovado" ? "REPROVADO" : "VÁLIDO"}
                                    </span>
                                    {revStatus === "reprovado" ? (
                                      <button
                                        title="Desfazer reprovação"
                                        onClick={() => handleToggleReprovacao(s.token, false)}
                                        className="p-1 text-xs font-bold bg-gray-500 hover:bg-gray-600 text-white rounded transition-colors"
                                      >
                                        ↶
                                      </button>
                                    ) : (
                                      <button
                                        title="Reprovar submissão"
                                        onClick={() => handleToggleReprovacao(s.token, true)}
                                        className="p-1 text-xs font-bold bg-red-600 hover:bg-red-700 text-white rounded transition-colors"
                                      >
                                        ✗
                                      </button>
                                    )}
                                  </div>
                                ) : (
                                  <span className="text-xs text-gray-400">N/A (Legado)</span>
                                )}
                              </td>
                              <td className="py-2 px-4 text-right text-gray-700">{s.points}</td>
                              <td className="py-2 px-4 text-gray-500">{formatDateTime(s.submitted_at)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                  <div className="flex items-center justify-between mt-3 px-1 text-sm text-gray-600 flex-wrap gap-2">
                    <div>
                      Mostrando{" "}
                      <span className="font-semibold text-gray-800">
                        {submissoesFiltradas.length > 0
                          ? (paginaSubmissoes - 1) * TAMANHO_PAGINA_SUBMISSOES + 1
                          : 0}
                      </span>{" "}
                      a{" "}
                      <span className="font-semibold text-gray-800">
                        {Math.min(paginaSubmissoes * TAMANHO_PAGINA_SUBMISSOES, submissoesFiltradas.length)}
                      </span>{" "}
                      de <span className="font-semibold text-gray-800">{submissoesFiltradas.length}</span> submissões
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setPaginaSubmissoes((p) => Math.max(1, p - 1))}
                        disabled={paginaSubmissoes === 1}
                        className="px-3 py-1.5 text-xs font-medium bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                      >
                        ← Anterior
                      </button>
                      <span className="text-xs font-medium text-gray-700 px-1">
                        Página {paginaSubmissoes} de {totalPaginasSubmissoes}
                      </span>
                      <button
                        type="button"
                        onClick={() => setPaginaSubmissoes((p) => Math.min(totalPaginasSubmissoes, p + 1))}
                        disabled={paginaSubmissoes >= totalPaginasSubmissoes}
                        className="px-3 py-1.5 text-xs font-medium bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                      >
                        Próxima →
                      </button>
                    </div>
                  </div>
                </>
              )}
            </div>
          </>
        ) : null}
      </div>
    );
  } else if (desafioView.name === "submissao") {
    conteudoDesafios = (
      <div className="space-y-6">
        <button onClick={() => setDesafioView({ name: "lista" })} className="text-gray-500 hover:text-gray-700 text-sm">
          ← Voltar
        </button>

        {erroSubmissao && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">{erroSubmissao}</div>
        )}

        {loadingSubmissao ? (
          <p className="text-gray-500">Carregando submissão...</p>
        ) : submissaoAtual ? (
          <SubmissionDetail
            submissao={submissaoAtual}
            onShowVersions={() => abrirVersoes(submissaoAtual.token)}
            onOpenSyncRun={abrirExecucao}
          />
        ) : null}
      </div>
    );
  } else {
    // desafioView.name === "versoes"
    conteudoDesafios = (
      <div className="space-y-6">
        <button
          onClick={() => setDesafioView({ name: "submissao", token: desafioView.token })}
          className="text-gray-500 hover:text-gray-700 text-sm"
        >
          ← Voltar
        </button>

        <h3 className="text-lg font-bold text-gray-800">Histórico de versões</h3>

        {erroVersoes && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">{erroVersoes}</div>
        )}

        {loadingVersoes ? (
          <p className="text-gray-500">Carregando histórico...</p>
        ) : versoes.length === 0 ? (
          <p className="text-gray-500">Nenhuma versão registrada para este token.</p>
        ) : (
          <div className="space-y-4">
            {versoes.map((v) => (
              <div key={v.id} className="bg-white rounded-xl border border-gray-200 p-4 space-y-3 text-sm">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <h4 className="font-semibold text-gray-800">Versão {v.version_number}</h4>
                  <button
                    type="button"
                    onClick={() => abrirExecucao(v.sync_run_id)}
                    className="text-indigo-600 hover:underline text-xs"
                  >
                    Execução #{v.sync_run_id}
                  </button>
                </div>

                <p className="text-gray-500">Observado em: {formatDateTime(v.observed_at)}</p>

                <div>
                  <p className="text-gray-500">Motivo:</p>
                  <p className="font-medium text-gray-800">{v.change_reason}</p>
                </div>

                <p>
                  Δ pontos:{" "}
                  <strong className={v.point_delta >= 0 ? "text-green-600" : "text-red-600"}>
                    {v.point_delta >= 0 ? "+" : ""}
                    {v.point_delta}
                  </strong>
                </p>

                <div>
                  <p className="font-medium text-gray-700 mb-1">Δ por clã</p>
                  <ClanDeltaList deltas={v.clan_deltas} />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Estado anterior</p>
                    <pre className="bg-gray-50 rounded p-2 text-xs overflow-x-auto">
                      {v.previous_state ? JSON.stringify(v.previous_state, null, 2) : "—"}
                    </pre>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Estado atual</p>
                    <pre className="bg-gray-50 rounded p-2 text-xs overflow-x-auto">
                      {JSON.stringify(v.current_state, null, 2)}
                    </pre>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // --- Aba Sincronizações ---

  let conteudoSincronizacoes: React.ReactNode;

  if (syncView.name === "lista") {
    conteudoSincronizacoes = (
      <div className="space-y-4">
        {erroExecucoes && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">{erroExecucoes}</div>
        )}

        {loadingExecucoes ? (
          <p className="text-gray-500">Carregando sincronizações...</p>
        ) : execucoes.length === 0 ? (
          <p className="text-gray-500">Nenhuma sincronização registrada.</p>
        ) : (
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200 text-left text-gray-500">
                  <th className="py-3 px-4 font-medium">Execução</th>
                  <th className="py-3 px-4 font-medium">Iniciada em</th>
                  <th className="py-3 px-4 font-medium">Status</th>
                  <th className="py-3 px-4 font-medium text-center">Linhas</th>
                  <th className="py-3 px-4 font-medium text-center">Criados/Arquivados/Reativados</th>
                </tr>
              </thead>
              <tbody>
                {execucoes.map((e) => (
                  <tr key={e.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="py-3 px-4">
                      <button
                        onClick={() => setSyncView({ name: "detalhe", runId: e.id })}
                        className="font-medium text-indigo-600 hover:underline"
                      >
                        #{e.id}
                      </button>
                    </td>
                    <td className="py-3 px-4 text-gray-600">{formatDateTime(e.started_at)}</td>
                    <td className="py-3 px-4 text-gray-600">{e.status}</td>
                    <td className="py-3 px-4 text-center text-gray-600">{e.sheet_row_count}</td>
                    <td className="py-3 px-4 text-center text-gray-600">
                      {e.challenges_created} / {e.challenges_archived} / {e.challenges_reactivated}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  } else {
    conteudoSincronizacoes = (
      <div className="space-y-6">
        <button
          onClick={() => setSyncView({ name: "lista" })}
          className="text-gray-500 hover:text-gray-700 text-sm"
        >
          ← Sincronizações
        </button>

        {erroExecucao && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">{erroExecucao}</div>
        )}

        {loadingExecucao ? (
          <p className="text-gray-500">Carregando execução...</p>
        ) : execucaoAtual ? (
          <SyncRunDetail execucao={execucaoAtual} />
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <h2 className="text-2xl font-bold text-gray-800">Desafios</h2>
        {tokenSearchBox}
      </div>

      {erroBuscaToken && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">{erroBuscaToken}</div>
      )}

      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8" aria-label="Tabs">
          <button
            onClick={() => setAba("desafios")}
            className={tabClass(aba === "desafios")}
          >
            Desafios
          </button>
          <button
            onClick={() => setAba("sincronizacoes")}
            className={tabClass(aba === "sincronizacoes")}
          >
            Sincronizações
          </button>
        </nav>
      </div>

      {aba === "desafios" ? conteudoDesafios : conteudoSincronizacoes}
    </div>
  );
}
