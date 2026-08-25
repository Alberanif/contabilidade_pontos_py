import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Desafios from "./Desafios";
import {
  fetchDesafiosAuditoria,
  fetchDesafioAuditoria,
  fetchSubmissoesDoDesafio,
  fetchSubmissaoPorToken,
  fetchVersoesDaSubmissao,
  fetchSincronizacoes,
  fetchSincronizacao,
  type DesafioAuditoria,
  type DesafioAuditoriaDetalhe,
  type DesafioSubmissao,
  type DesafioSubmissaoVersao,
  type DesafioSincronizacao,
} from "../api/client";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    fetchDesafiosAuditoria: vi.fn(),
    fetchDesafioAuditoria: vi.fn(),
    fetchSubmissoesDoDesafio: vi.fn(),
    fetchSubmissaoPorToken: vi.fn(),
    fetchVersoesDaSubmissao: vi.fn(),
    fetchSincronizacoes: vi.fn(),
    fetchSincronizacao: vi.fn(),
  };
});

function buildDesafio(overrides: Partial<DesafioAuditoria> = {}): DesafioAuditoria {
  return {
    id: 1,
    nome: "Semana de Treinos",
    contabilizar_pontos: true,
    data: null,
    data_inicio: "2026-08-01",
    data_fim: "2026-08-10",
    origem: "google_sheets",
    nome_normalizado: "semana de treinos",
    status: "ativo",
    arquivado_at: null,
    reativado_at: null,
    updated_at: "2026-08-10T12:00:00",
    created_at: "2026-08-01T09:00:00",
    ...overrides,
  };
}

function buildDetalhe(overrides: Partial<DesafioAuditoriaDetalhe> = {}): DesafioAuditoriaDetalhe {
  return {
    ...buildDesafio(),
    pontos_por_clan: { "CLÃ 1": 120, "CLÃ 2": 80 },
    ...overrides,
  };
}

function buildSubmissao(overrides: Partial<DesafioSubmissao> = {}): DesafioSubmissao {
  return {
    token: "tok-abc123",
    row_numbers: [42],
    raw_cells: ["CLÃ 1", "Fulano", "Sim", "http://link", "obs livre", "Semana de Treinos", "CLÃ 1", "2026-08-05 10:00:00", "tok-abc123"],
    raw_clan_legacy: "CLÃ 1",
    raw_name: "Fulano",
    raw_validation: "Sim",
    raw_link: "http://link",
    raw_observation: "obs livre",
    raw_challenge: "Semana de Treinos",
    raw_clan_current: "CLÃ 1",
    raw_submitted_at: "2026-08-05 10:00:00",
    raw_token: "tok-abc123",
    clan: "CLÃ 1",
    challenge_normalized: "semana de treinos",
    desafio_id: 1,
    submitted_at: "2026-08-05T10:00:00",
    status: "active_counted",
    invalid_reasons: [],
    points: 10,
    content_hash: "hash-1",
    first_seen_run_id: 5,
    last_seen_run_id: 7,
    inactivated_at: null,
    created_at: "2026-08-05T10:05:00",
    updated_at: "2026-08-06T08:00:00",
    ...overrides,
  };
}

function buildVersao(overrides: Partial<DesafioSubmissaoVersao> = {}): DesafioSubmissaoVersao {
  return {
    id: 1,
    token: "tok-abc123",
    sync_run_id: 7,
    version_number: 2,
    row_numbers: [42],
    raw_cells: [],
    raw_clan_legacy: "CLÃ 1",
    raw_name: "Fulano",
    raw_validation: "Sim",
    raw_link: "http://link",
    raw_observation: "obs livre",
    raw_challenge: "Semana de Treinos",
    raw_clan_current: "CLÃ 1",
    raw_submitted_at: "2026-08-05 10:00:00",
    raw_token: "tok-abc123",
    previous_state: { status: "active_not_counted" },
    current_state: { status: "active_counted" },
    previous_status: "active_not_counted",
    current_status: "active_counted",
    point_delta: 10,
    clan_deltas: { "CLÃ 1": 6, "CLÃ 2": 4 },
    change_reason: "revalidated",
    observed_at: "2026-08-06T08:00:00",
    ...overrides,
  };
}

function buildExecucao(overrides: Partial<DesafioSincronizacao> = {}): DesafioSincronizacao {
  return {
    id: 7,
    started_at: "2026-08-06T07:55:00",
    finished_at: "2026-08-06T08:00:00",
    status: "succeeded",
    snapshot_hash: "hash-run-7",
    sheet_row_count: 50,
    state_counts: { new: 1, unchanged: 48, missing: 1 },
    clan_deltas: { "CLÃ 1": 10 },
    challenges_created: 0,
    challenges_archived: 0,
    challenges_reactivated: 0,
    points_per_submission: 10,
    mass_removal_required: false,
    mass_removal_confirmed: false,
    mass_removal_count: 0,
    error: null,
    created_at: "2026-08-06T08:00:00",
    ...overrides,
  };
}

describe("Desafios (tela de consulta e auditoria)", () => {
  beforeEach(() => {
    vi.mocked(fetchDesafiosAuditoria).mockReset().mockResolvedValue([buildDesafio()]);
    vi.mocked(fetchDesafioAuditoria).mockReset().mockResolvedValue(buildDetalhe());
    vi.mocked(fetchSubmissoesDoDesafio).mockReset().mockResolvedValue([buildSubmissao()]);
    vi.mocked(fetchSubmissaoPorToken).mockReset().mockResolvedValue(buildSubmissao());
    vi.mocked(fetchVersoesDaSubmissao).mockReset().mockResolvedValue([buildVersao()]);
    vi.mocked(fetchSincronizacoes).mockReset().mockResolvedValue([buildExecucao()]);
    vi.mocked(fetchSincronizacao).mockReset().mockResolvedValue(buildExecucao());
  });

  // --- Step 1: ausência de mutação, presença de filtros e do toggle ---

  it("lists active desafios by default with no create/edit/delete/manual-register/csv-import affordance anywhere", async () => {
    render(<Desafios />);

    expect(await screen.findByText("Semana de Treinos")).toBeInTheDocument();
    expect(fetchDesafiosAuditoria).toHaveBeenCalledWith("active");

    for (const name of [
      /novo desafio/i,
      /criar desafio/i,
      /^criar$/i,
      /^editar$/i,
      /^excluir$/i,
      /importar csv/i,
      /adicionar cl[ãa]/i,
      /registrar/i,
      /salvar desafio/i,
    ]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
    expect(screen.queryByRole("textbox", { name: /nome do desafio/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
  });

  it("toggles between active and archived desafios via the status filter", async () => {
    const user = userEvent.setup();
    render(<Desafios />);
    await screen.findByText("Semana de Treinos");

    await user.click(screen.getByRole("button", { name: /arquivados/i }));
    await waitFor(() => expect(fetchDesafiosAuditoria).toHaveBeenLastCalledWith("archived"));

    await user.click(screen.getByRole("button", { name: /todos/i }));
    await waitFor(() => expect(fetchDesafiosAuditoria).toHaveBeenLastCalledWith("all"));
  });

  it("shows a token search box that performs a direct lookup, not a list-substring filter", async () => {
    const user = userEvent.setup();
    render(<Desafios />);
    await screen.findByText("Semana de Treinos");

    const input = screen.getByLabelText(/token/i);
    await user.type(input, "tok-abc123");
    await user.click(screen.getByRole("button", { name: /buscar/i }));

    await waitFor(() => expect(fetchSubmissaoPorToken).toHaveBeenCalledWith("tok-abc123"));
    const detail = await screen.findByTestId("submission-detail");
    expect(within(detail).getAllByText("tok-abc123").length).toBeGreaterThan(0);
  });

  it("shows an error, without navigating, when a searched token is not found", async () => {
    vi.mocked(fetchSubmissaoPorToken).mockReset().mockRejectedValue(new Error("Token de submissão não encontrado"));
    const user = userEvent.setup();
    render(<Desafios />);
    await screen.findByText("Semana de Treinos");

    await user.type(screen.getByLabelText(/token/i), "desconhecido");
    await user.click(screen.getByRole("button", { name: /buscar/i }));

    expect(await screen.findByText(/token de submiss[ãa]o n[ãa]o encontrado/i)).toBeInTheDocument();
    expect(screen.getByText("Semana de Treinos")).toBeInTheDocument();
  });

  it("shows a loading state then an empty state when there are no desafios", async () => {
    let resolvePromise: (value: DesafioAuditoria[]) => void = () => {};
    const promise = new Promise<DesafioAuditoria[]>((resolve) => {
      resolvePromise = resolve;
    });
    vi.mocked(fetchDesafiosAuditoria).mockReset().mockReturnValue(promise);

    render(<Desafios />);
    expect(screen.getByText(/carregando/i)).toBeInTheDocument();

    resolvePromise([]);
    expect(await screen.findByText(/nenhum desafio encontrado/i)).toBeInTheDocument();
  });

  it("shows an error state when the desafios list fetch fails", async () => {
    vi.mocked(fetchDesafiosAuditoria).mockReset().mockRejectedValue(new Error("Erro de rede"));
    render(<Desafios />);
    expect(await screen.findByText(/erro de rede/i)).toBeInTheDocument();
  });

  it("drills into a desafio to show pontos_por_clan totals and clan/status/period filters combined server-side", async () => {
    const user = userEvent.setup();
    render(<Desafios />);
    await user.click(await screen.findByText("Semana de Treinos"));

    const pontosPorClan = await screen.findByTestId("pontos-por-clan");
    expect(within(pontosPorClan).getByText("CLÃ 1")).toBeInTheDocument();
    expect(within(pontosPorClan).getByText("120")).toBeInTheDocument();
    expect(fetchDesafioAuditoria).toHaveBeenCalledWith(1);
    expect(fetchSubmissoesDoDesafio).toHaveBeenCalledWith(1, expect.objectContaining({}));

    const clanInput = screen.getByLabelText(/^cl[ãa]$/i);
    await user.type(clanInput, "CLÃ 1");
    await waitFor(() =>
      expect(fetchSubmissoesDoDesafio).toHaveBeenLastCalledWith(
        1,
        expect.objectContaining({ clan: "CLÃ 1" })
      )
    );

    const statusSelect = screen.getByLabelText(/^status$/i);
    await user.selectOptions(statusSelect, "active_counted");
    await waitFor(() =>
      expect(fetchSubmissoesDoDesafio).toHaveBeenLastCalledWith(
        1,
        expect.objectContaining({ clan: "CLÃ 1", status: "active_counted" })
      )
    );
  });

  it("applies the período filter client-side over already-fetched submissions", async () => {
    vi.mocked(fetchSubmissoesDoDesafio).mockReset().mockResolvedValue([
      buildSubmissao({ token: "tok-in-range", submitted_at: "2026-08-05T10:00:00" }),
      buildSubmissao({ token: "tok-out-of-range", submitted_at: "2026-08-20T10:00:00" }),
    ]);
    const user = userEvent.setup();
    render(<Desafios />);
    await user.click(await screen.findByText("Semana de Treinos"));

    expect(await screen.findByText("tok-in-range")).toBeInTheDocument();
    expect(screen.getByText("tok-out-of-range")).toBeInTheDocument();

    await user.type(screen.getByLabelText(/enviado a partir de/i), "2026-08-01");
    await user.type(screen.getByLabelText(/enviado at[ée]/i), "2026-08-10");

    await waitFor(() => expect(screen.queryByText("tok-out-of-range")).not.toBeInTheDocument());
    expect(screen.getByText("tok-in-range")).toBeInTheDocument();
    // Client-side filtering must not trigger new server calls per keystroke on dates.
    expect(fetchSubmissoesDoDesafio).toHaveBeenCalledTimes(1);
  });

  // --- Step 2: detalhe de token (A-I, motivos, link, observação, estado atual) e histórico de versões ---

  it("shows the token detail with the 9 raw A-I fields in sheet order, current state and invalid reasons", async () => {
    vi.mocked(fetchSubmissaoPorToken).mockReset().mockResolvedValue(
      buildSubmissao({
        status: "invalid",
        invalid_reasons: ["clã desconhecido", "data fora do período"],
      })
    );
    const user = userEvent.setup();
    render(<Desafios />);
    await screen.findByText("Semana de Treinos");

    await user.type(screen.getByLabelText(/token/i), "tok-abc123");
    await user.click(screen.getByRole("button", { name: /buscar/i }));

    const detail = await screen.findByTestId("submission-detail");
    expect(within(detail).getAllByText("tok-abc123").length).toBeGreaterThan(0);

    // Current state.
    const currentState = within(detail).getByTestId("current-state");
    expect(within(currentState).getByText("CLÃ 1")).toBeInTheDocument();
    expect(within(currentState).getByText("semana de treinos")).toBeInTheDocument();
    expect(within(currentState).getByText("10")).toBeInTheDocument();

    // Invalid reasons.
    expect(within(detail).getByText("clã desconhecido")).toBeInTheDocument();
    expect(within(detail).getByText("data fora do período")).toBeInTheDocument();

    // The 9 raw A-I fields, in order.
    const rawTable = within(detail).getByTestId("raw-fields-table");
    const rowTexts = within(rawTable)
      .getAllByRole("row")
      .slice(1) // skip header row
      .map((row) => row.textContent ?? "");
    expect(rowTexts).toHaveLength(9);
    expect(rowTexts[0]).toContain("CLÃ 1"); // raw_clan_legacy (A)
    expect(rowTexts[1]).toContain("Fulano"); // raw_name (B)
    expect(rowTexts[2]).toContain("Sim"); // raw_validation (C)
    expect(rowTexts[3]).toContain("http://link"); // raw_link (D)
    expect(rowTexts[4]).toContain("obs livre"); // raw_observation (E)
    expect(rowTexts[5]).toContain("Semana de Treinos"); // raw_challenge (F)
    expect(rowTexts[6]).toContain("CLÃ 1"); // raw_clan_current (G)
    expect(rowTexts[7]).toContain("2026-08-05 10:00:00"); // raw_submitted_at (H)
    expect(rowTexts[8]).toContain("tok-abc123"); // raw_token (I)

    // Link to version history.
    expect(within(detail).getByRole("button", { name: /hist[óo]rico de vers(õ|o)es/i })).toBeInTheDocument();
  });

  it("navigates from a token detail to its version/delta history", async () => {
    const user = userEvent.setup();
    render(<Desafios />);
    await screen.findByText("Semana de Treinos");

    await user.type(screen.getByLabelText(/token/i), "tok-abc123");
    await user.click(screen.getByRole("button", { name: /buscar/i }));
    await screen.findByTestId("submission-detail");

    await user.click(screen.getByRole("button", { name: /hist[óo]rico de vers(õ|o)es/i }));

    expect(fetchVersoesDaSubmissao).toHaveBeenCalledWith("tok-abc123");
    expect(await screen.findByText(/vers[ãa]o 2/i)).toBeInTheDocument();
    expect(screen.getByText("revalidated")).toBeInTheDocument();
    expect(screen.getByText(/\+10/)).toBeInTheDocument();
    expect(screen.getByText(/active_not_counted/)).toBeInTheDocument();
    expect(screen.getByText(/active_counted/)).toBeInTheDocument();
  });

  it("navigates from a sync run's own id back to that run's detail via a submission's first/last seen run", async () => {
    const user = userEvent.setup();
    render(<Desafios />);
    await screen.findByText("Semana de Treinos");

    await user.type(screen.getByLabelText(/token/i), "tok-abc123");
    await user.click(screen.getByRole("button", { name: /buscar/i }));
    await screen.findByTestId("submission-detail");

    await user.click(screen.getByRole("button", { name: /execu[çc][ãa]o #7/i }));

    await waitFor(() => expect(fetchSincronizacao).toHaveBeenCalledWith(7));
    expect(await screen.findByTestId("sync-run-detail")).toBeInTheDocument();
  });

  it("browses sync runs and drills into one run's detail", async () => {
    const user = userEvent.setup();
    render(<Desafios />);
    await screen.findByText("Semana de Treinos");

    await user.click(screen.getByRole("button", { name: "Sincronizações" }));
    expect(fetchSincronizacoes).toHaveBeenCalled();
    await user.click(await screen.findByText("#7"));

    expect(await screen.findByTestId("sync-run-detail")).toBeInTheDocument();
    expect(fetchSincronizacao).toHaveBeenCalledWith(7);
    expect(screen.getAllByText(/succeeded|sucesso/i).length).toBeGreaterThan(0);
  });
});
