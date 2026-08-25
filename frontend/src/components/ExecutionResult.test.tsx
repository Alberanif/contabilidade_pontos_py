import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ExecutionResult from "./ExecutionResult";
import { confirmarDesafios, type DesafioSyncResult } from "../api/client";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    confirmarDesafios: vi.fn(),
  };
});

function buildResult(overrides: Partial<DesafioSyncResult> = {}): DesafioSyncResult {
  return {
    status: "success",
    run_id: 1,
    snapshot_hash: "hash-1",
    sheet_row_count: 10,
    state_counts: {},
    clan_deltas: {},
    clan_totals_after: {},
    challenges_created: 0,
    challenges_archived: 0,
    challenges_reactivated: 0,
    tokens_versioned: 0,
    duration_seconds: 1.2,
    mensagem: "",
    active_tokens_before: null,
    mass_removal_required: false,
    mass_removal_count: 0,
    mass_removal_ratio: 0,
    ...overrides,
  };
}

describe("ExecutionResult", () => {
  beforeEach(() => {
    vi.mocked(confirmarDesafios).mockReset();
  });

  it("renders success state with row count, state breakdown, clan deltas and duration", () => {
    const result = buildResult({
      status: "success",
      mensagem: "3 nova(s) submissão(ões) de desafio.",
      sheet_row_count: 42,
      state_counts: { new: 3, unchanged: 39, missing: 1, invalid: 0, conflicted: 0 },
      clan_deltas: { "CLÃ 1": 40, "CLÃ 3": -10 },
      challenges_created: 1,
      challenges_archived: 0,
      challenges_reactivated: 2,
      tokens_versioned: 4,
      duration_seconds: 2.345,
    });

    render(<ExecutionResult desafios={result} />);

    expect(screen.getByText(/3 nova\(s\) submissão\(ões\) de desafio\./)).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("2.3s")).toBeInTheDocument();
    expect(screen.getByText("Novos")).toBeInTheDocument();
    expect(screen.getByText("Inativados")).toBeInTheDocument();
    expect(screen.getByText("CLÃ 1")).toBeInTheDocument();
    expect(screen.getByText("+40")).toBeInTheDocument();
    expect(screen.getByText("CLÃ 3")).toBeInTheDocument();
    expect(screen.getByText("-10")).toBeInTheDocument();
  });

  it("shows an isolated desafios failure without hiding sibling success content from other sources", () => {
    const result = buildResult({ status: "failed", mensagem: "Timeout ao ler planilha" });

    render(
      <div>
        <p>Coaching Individual contabilizados: 12</p>
        <ExecutionResult desafios={result} />
      </div>
    );

    expect(screen.getByText("Coaching Individual contabilizados: 12")).toBeInTheDocument();
    expect(screen.getByText(/Timeout ao ler planilha/)).toBeInTheDocument();
    expect(screen.getByText(/Execute a contabilidade novamente/i)).toBeInTheDocument();
  });

  it("shows a neutral message when clan deltas are zero", () => {
    const result = buildResult({
      status: "success",
      mensagem: "Desafios sincronizados: nenhuma alteração desde a última execução.",
      tokens_versioned: 0,
      clan_deltas: {},
    });

    render(<ExecutionResult desafios={result} />);

    expect(screen.getByText(/nenhuma alteração desde a última execução/)).toBeInTheDocument();
    expect(screen.getByText(/Nenhuma alteração nos clãs/)).toBeInTheDocument();
  });

  it("shows per-clan impact and sends the confirmation request on awaiting_confirmation", async () => {
    const user = userEvent.setup();
    const pending = buildResult({
      status: "awaiting_confirmation",
      snapshot_hash: "hash-abc",
      mensagem: "Confirmação necessária: 5 token(s) ativo(s) deixariam de pontuar (40% dos ativos).",
      active_tokens_before: 12,
      mass_removal_required: true,
      mass_removal_count: 5,
      mass_removal_ratio: 0.4,
      clan_deltas: { "CLÃ 1": -30, "CLÃ 2": -20 },
    });
    const confirmed = buildResult({
      status: "success",
      mensagem: "5 removida(s).",
      snapshot_hash: "hash-abc",
      clan_deltas: { "CLÃ 1": -30, "CLÃ 2": -20 },
      clan_totals_after: { "CLÃ 1": 70, "CLÃ 2": 80 },
    });
    vi.mocked(confirmarDesafios).mockResolvedValueOnce(confirmed);
    const onConfirmed = vi.fn();

    render(<ExecutionResult desafios={pending} onConfirmed={onConfirmed} />);

    expect(screen.getByText("40%")).toBeInTheDocument();
    expect(screen.getByText("CLÃ 1")).toBeInTheDocument();
    expect(screen.getByText("-30")).toBeInTheDocument();
    expect(screen.getByText("CLÃ 2")).toBeInTheDocument();
    expect(screen.getByText("-20")).toBeInTheDocument();

    const button = screen.getByRole("button", { name: /confirmar remoção em massa/i });
    await user.click(button);

    expect(confirmarDesafios).toHaveBeenCalledTimes(1);
    expect(confirmarDesafios).toHaveBeenCalledWith("hash-abc", true);
    await waitFor(() => expect(screen.getByText(/5 removida\(s\)\./)).toBeInTheDocument());
    expect(onConfirmed).toHaveBeenCalledWith(confirmed);
  });

  it("disables the confirm button while the confirmation request is in flight", async () => {
    const user = userEvent.setup();
    let resolvePromise: (value: DesafioSyncResult) => void = () => {};
    const promise = new Promise<DesafioSyncResult>((resolve) => {
      resolvePromise = resolve;
    });
    vi.mocked(confirmarDesafios).mockReturnValueOnce(promise);

    const pending = buildResult({
      status: "awaiting_confirmation",
      snapshot_hash: "hash-abc",
      mass_removal_required: true,
      mass_removal_count: 5,
      mass_removal_ratio: 0.4,
    });

    render(<ExecutionResult desafios={pending} />);
    const button = screen.getByRole("button", { name: /confirmar remoção em massa/i });
    await user.click(button);

    expect(button).toBeDisabled();
    expect(confirmarDesafios).toHaveBeenCalledTimes(1);

    resolvePromise(buildResult({ status: "success" }));
    // Após a resposta, o status muda para "success" e o botão de confirmação
    // some — provando que não houve um segundo clique/segunda chamada.
    await waitFor(() => expect(screen.queryByRole("button")).not.toBeInTheDocument());
    expect(confirmarDesafios).toHaveBeenCalledTimes(1);
  });

  it("treats a stale snapshot rejected on confirmation as a failure requiring a fresh run", async () => {
    const user = userEvent.setup();
    const pending = buildResult({
      status: "awaiting_confirmation",
      snapshot_hash: "hash-old",
      mass_removal_required: true,
      mass_removal_count: 5,
      mass_removal_ratio: 0.4,
    });
    const staleFailure = buildResult({
      status: "failed",
      snapshot_hash: "hash-new",
      mensagem:
        "confirmação não corresponde ao snapshot atual (confirmado 'hash-old', plano 'hash-new')",
    });
    vi.mocked(confirmarDesafios).mockResolvedValueOnce(staleFailure);

    render(<ExecutionResult desafios={pending} />);
    await user.click(screen.getByRole("button", { name: /confirmar remoção em massa/i }));

    await waitFor(() =>
      expect(screen.getByText(/não corresponde ao snapshot atual/)).toBeInTheDocument()
    );
    expect(screen.getByText(/Execute a contabilidade novamente/i)).toBeInTheDocument();
    // Não deve mais mostrar o fluxo de confirmação antigo.
    expect(screen.queryByRole("button", { name: /confirmar remoção em massa/i })).not.toBeInTheDocument();
  });

  it("shows already_running non-destructively, without an error style or a confirm button", () => {
    const result = buildResult({
      status: "already_running",
      mensagem: "Uma sincronização de desafios já está em andamento.",
    });

    render(<ExecutionResult desafios={result} />);

    expect(screen.getByText(/já está em andamento/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
