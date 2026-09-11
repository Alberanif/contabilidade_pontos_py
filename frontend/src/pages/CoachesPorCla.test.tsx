import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CoachesPorCla from "./CoachesPorCla";
import {
  fetchCoachClas,
  createCoachCla,
  updateCoachCla,
  deleteCoachCla,
  type CoachCla,
} from "../api/client";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    fetchCoachClas: vi.fn(),
    createCoachCla: vi.fn(),
    updateCoachCla: vi.fn(),
    deleteCoachCla: vi.fn(),
  };
});

function buildCoachCla(overrides: Partial<CoachCla> = {}): CoachCla {
  return {
    coach_canonico: "Ana Albertim",
    clan: "CLÃ 1",
    categoria: "Ouro",
    ...overrides,
  };
}

describe("CoachesPorCla (listagem somente leitura)", () => {
  beforeEach(() => {
    vi.mocked(fetchCoachClas).mockReset();
  });

  it("groups coaches by clã, showing each coach's name and categoria under its clã section", async () => {
    vi.mocked(fetchCoachClas).mockResolvedValue([
      buildCoachCla({ coach_canonico: "Ana Albertim", clan: "CLÃ 1", categoria: "Ouro" }),
      buildCoachCla({ coach_canonico: "Bruno Silva", clan: "CLÃ 1", categoria: "Prata" }),
      buildCoachCla({ coach_canonico: "Carla Souza", clan: "CLÃ 2", categoria: "Bronze" }),
    ]);

    render(<CoachesPorCla />);

    expect(fetchCoachClas).toHaveBeenCalled();

    const clan1 = await screen.findByTestId("clan-section-CLÃ 1");
    expect(within(clan1).getByText("Ana Albertim")).toBeInTheDocument();
    expect(within(clan1).getByText("Ouro")).toBeInTheDocument();
    expect(within(clan1).getByText("Bruno Silva")).toBeInTheDocument();
    expect(within(clan1).getByText("Prata")).toBeInTheDocument();

    const clan2 = screen.getByTestId("clan-section-CLÃ 2");
    expect(within(clan2).getByText("Carla Souza")).toBeInTheDocument();
    expect(within(clan2).getByText("Bronze")).toBeInTheDocument();
    // Coach de outro clã não deve vazar para esta seção.
    expect(within(clan2).queryByText("Ana Albertim")).not.toBeInTheDocument();
  });

  it("shows an empty state and no clã sections when there are no coaches yet", async () => {
    vi.mocked(fetchCoachClas).mockResolvedValue([]);

    render(<CoachesPorCla />);

    expect(await screen.findByText(/nenhum coach/i)).toBeInTheDocument();
    expect(screen.queryByTestId(/^clan-section-/)).not.toBeInTheDocument();
  });

  it("filters the displayed list by coach name across all clãs, client-side", async () => {
    vi.mocked(fetchCoachClas).mockResolvedValue([
      buildCoachCla({ coach_canonico: "Ana Albertim", clan: "CLÃ 1", categoria: "Ouro" }),
      buildCoachCla({ coach_canonico: "Bruno Silva", clan: "CLÃ 1", categoria: "Prata" }),
      buildCoachCla({ coach_canonico: "Carla Souza", clan: "CLÃ 2", categoria: "Bronze" }),
    ]);

    const user = userEvent.setup();
    render(<CoachesPorCla />);

    await screen.findByText("Ana Albertim");
    expect(fetchCoachClas).toHaveBeenCalledTimes(1);

    const searchInput = screen.getByLabelText(/buscar por nome/i);
    await user.type(searchInput, "carla");

    await waitFor(() => expect(screen.queryByText("Ana Albertim")).not.toBeInTheDocument());
    expect(screen.queryByText("Bruno Silva")).not.toBeInTheDocument();
    expect(screen.getByText("Carla Souza")).toBeInTheDocument();

    // Clã sections with no matches after filtering should not remain empty on screen.
    expect(screen.queryByTestId("clan-section-CLÃ 1")).not.toBeInTheDocument();
    expect(screen.getByTestId("clan-section-CLÃ 2")).toBeInTheDocument();

    // Client-side filtering must not trigger new server calls per keystroke.
    expect(fetchCoachClas).toHaveBeenCalledTimes(1);
  });

  it("shows an error state when the fetch fails", async () => {
    vi.mocked(fetchCoachClas).mockRejectedValue(new Error("Erro de rede"));

    render(<CoachesPorCla />);

    expect(await screen.findByText(/erro de rede/i)).toBeInTheDocument();
  });

  it("does not render any points/totals anywhere on the page", async () => {
    vi.mocked(fetchCoachClas).mockResolvedValue([
      buildCoachCla({ coach_canonico: "Ana Albertim", clan: "CLÃ 1", categoria: "Ouro" }),
    ]);

    render(<CoachesPorCla />);

    await screen.findByText("Ana Albertim");
    expect(screen.queryByText(/pontos/i)).not.toBeInTheDocument();
  });

});

// CRUD pela UI (issue #7 / Task 7): adicionar, mover de clã, editar categoria
// e remover um coach, tudo pelo formulário/ações da própria página, sem SQL
// ou reimportação de CSV. Substitui a antiga suíte "read-only" desta página
// (issue #6), que agora não se aplica mais.
describe("CoachesPorCla (CRUD - issue #7)", () => {
  beforeEach(() => {
    vi.mocked(fetchCoachClas).mockReset();
    vi.mocked(createCoachCla).mockReset();
    vi.mocked(updateCoachCla).mockReset();
    vi.mocked(deleteCoachCla).mockReset();
  });

  it("adds a new coach through the form, refreshing the list afterwards", async () => {
    vi.mocked(fetchCoachClas)
      .mockResolvedValueOnce([
        buildCoachCla({ coach_canonico: "Ana Albertim", clan: "CLÃ 1", categoria: "Coach" }),
      ])
      .mockResolvedValueOnce([
        buildCoachCla({ coach_canonico: "Ana Albertim", clan: "CLÃ 1", categoria: "Coach" }),
        buildCoachCla({ coach_canonico: "Novo Coach", clan: "CLÃ 3", categoria: "Coach Pro" }),
      ]);
    vi.mocked(createCoachCla).mockResolvedValue(
      buildCoachCla({ coach_canonico: "Novo Coach", clan: "CLÃ 3", categoria: "Coach Pro" })
    );

    const user = userEvent.setup();
    render(<CoachesPorCla />);
    await screen.findByText("Ana Albertim");

    await user.click(screen.getByRole("button", { name: /adicionar coach/i }));
    await user.type(screen.getByLabelText(/nome do coach/i), "Novo Coach");
    await user.selectOptions(screen.getByLabelText(/^clã$/i), "CLÃ 3");
    await user.selectOptions(screen.getByLabelText(/^categoria$/i), "Coach Pro");
    await user.click(screen.getByRole("button", { name: /^salvar$/i }));

    await waitFor(() =>
      expect(createCoachCla).toHaveBeenCalledWith({
        coach: "Novo Coach",
        clan: "CLÃ 3",
        categoria: "Coach Pro",
      })
    );
    expect(await screen.findByText("Novo Coach")).toBeInTheDocument();
    expect(fetchCoachClas).toHaveBeenCalledTimes(2);
    // O formulário fecha após sucesso.
    expect(screen.queryByLabelText(/nome do coach/i)).not.toBeInTheDocument();
  });

  it("shows a clear message instead of a generic error when adding conflicts with 409", async () => {
    vi.mocked(fetchCoachClas).mockResolvedValue([
      buildCoachCla({ coach_canonico: "Ana Albertim", clan: "CLÃ 1", categoria: "Coach" }),
    ]);
    const conflictError = new Error(
      "Coach 'Ana Albertim' já pertence ao clã 'CLÃ 1'. Use PUT /api/coach-clas/{coach_canonico} para mover de clã."
    ) as Error & { status?: number };
    conflictError.status = 409;
    vi.mocked(createCoachCla).mockRejectedValue(conflictError);

    const user = userEvent.setup();
    render(<CoachesPorCla />);
    await screen.findByText("Ana Albertim");

    await user.click(screen.getByRole("button", { name: /adicionar coach/i }));
    await user.type(screen.getByLabelText(/nome do coach/i), "Ana Albertim");
    await user.selectOptions(screen.getByLabelText(/^clã$/i), "CLÃ 2");
    await user.click(screen.getByRole("button", { name: /^salvar$/i }));

    expect(await screen.findByText(/este coach já está no clã 1/i)).toBeInTheDocument();
    expect(screen.getByText(/use "editar"/i)).toBeInTheDocument();
    // O formulário permanece aberto (não fecha em erro) e a lista não é
    // revalidada, já que a operação falhou.
    expect(screen.getByLabelText(/nome do coach/i)).toBeInTheDocument();
    expect(fetchCoachClas).toHaveBeenCalledTimes(1);
  });

  it("moves a coach to a different clã via the edit form (updateCoachCla)", async () => {
    vi.mocked(fetchCoachClas)
      .mockResolvedValueOnce([
        buildCoachCla({ coach_canonico: "Ana Albertim", clan: "CLÃ 1", categoria: "Coach" }),
      ])
      .mockResolvedValueOnce([
        buildCoachCla({ coach_canonico: "Ana Albertim", clan: "CLÃ 4", categoria: "Coach" }),
      ]);
    vi.mocked(updateCoachCla).mockResolvedValue(
      buildCoachCla({ coach_canonico: "Ana Albertim", clan: "CLÃ 4", categoria: "Coach" })
    );

    const user = userEvent.setup();
    render(<CoachesPorCla />);
    await screen.findByText("Ana Albertim");

    const row = screen.getByTestId("coach-row-Ana Albertim");
    await user.click(within(row).getByRole("button", { name: /^editar$/i }));

    // O nome do coach não é editável em modo edição (só clã/categoria mudam).
    expect(screen.getByLabelText(/nome do coach/i)).toBeDisabled();
    await user.selectOptions(screen.getByLabelText(/^clã$/i), "CLÃ 4");
    await user.click(screen.getByRole("button", { name: /^salvar$/i }));

    await waitFor(() =>
      expect(updateCoachCla).toHaveBeenCalledWith("Ana Albertim", { clan: "CLÃ 4", categoria: "Coach" })
    );
    expect(await screen.findByTestId("clan-section-CLÃ 4")).toBeInTheDocument();
    expect(screen.queryByTestId("clan-section-CLÃ 1")).not.toBeInTheDocument();
  });

  it("edits a coach's categoria via the edit form (updateCoachCla)", async () => {
    vi.mocked(fetchCoachClas)
      .mockResolvedValueOnce([
        buildCoachCla({ coach_canonico: "Ana Albertim", clan: "CLÃ 1", categoria: "Coach" }),
      ])
      .mockResolvedValueOnce([
        buildCoachCla({ coach_canonico: "Ana Albertim", clan: "CLÃ 1", categoria: "Coach Hero" }),
      ]);
    vi.mocked(updateCoachCla).mockResolvedValue(
      buildCoachCla({ coach_canonico: "Ana Albertim", clan: "CLÃ 1", categoria: "Coach Hero" })
    );

    const user = userEvent.setup();
    render(<CoachesPorCla />);
    await screen.findByText("Ana Albertim");

    const row = screen.getByTestId("coach-row-Ana Albertim");
    await user.click(within(row).getByRole("button", { name: /^editar$/i }));
    await user.selectOptions(screen.getByLabelText(/^categoria$/i), "Coach Hero");
    await user.click(screen.getByRole("button", { name: /^salvar$/i }));

    await waitFor(() =>
      expect(updateCoachCla).toHaveBeenCalledWith("Ana Albertim", { clan: "CLÃ 1", categoria: "Coach Hero" })
    );
    expect(await screen.findByText("Coach Hero")).toBeInTheDocument();
  });

  it("requires confirmation before removing a coach; cancel keeps it, confirm removes and refreshes", async () => {
    vi.mocked(fetchCoachClas)
      .mockResolvedValueOnce([
        buildCoachCla({ coach_canonico: "Ana Albertim", clan: "CLÃ 1", categoria: "Coach" }),
      ])
      .mockResolvedValueOnce([]);
    vi.mocked(deleteCoachCla).mockResolvedValue(undefined);

    const user = userEvent.setup();
    render(<CoachesPorCla />);
    await screen.findByText("Ana Albertim");

    const row = screen.getByTestId("coach-row-Ana Albertim");
    await user.click(within(row).getByRole("button", { name: /^remover$/i }));

    // Cancelar: coach permanece, deleteCoachCla não é chamado.
    await user.click(within(row).getByRole("button", { name: /^cancelar$/i }));
    expect(deleteCoachCla).not.toHaveBeenCalled();
    expect(screen.getByText("Ana Albertim")).toBeInTheDocument();

    // Confirmar: agora remove de fato.
    await user.click(within(row).getByRole("button", { name: /^remover$/i }));
    await user.click(within(row).getByRole("button", { name: /confirmar remoção/i }));

    await waitFor(() => expect(deleteCoachCla).toHaveBeenCalledWith("Ana Albertim"));
    await waitFor(() => expect(screen.queryByText("Ana Albertim")).not.toBeInTheDocument());
    expect(fetchCoachClas).toHaveBeenCalledTimes(2);
  });

  describe("paginação 'Ver mais' por clã", () => {
    function buildSeisCoachesDoClan1(): CoachCla[] {
      return Array.from({ length: 6 }, (_, i) =>
        buildCoachCla({ coach_canonico: `Coach ${i + 1}`, clan: "CLÃ 1", categoria: "Ouro" })
      );
    }

    it("mostra só os 5 primeiros coaches de um clã com mais de 5, com um botão 'Ver mais'", async () => {
      vi.mocked(fetchCoachClas).mockResolvedValue(buildSeisCoachesDoClan1());

      render(<CoachesPorCla />);

      const clan1 = await screen.findByTestId("clan-section-CLÃ 1");
      for (let i = 1; i <= 5; i++) {
        expect(within(clan1).getByText(`Coach ${i}`)).toBeInTheDocument();
      }
      expect(within(clan1).queryByText("Coach 6")).not.toBeInTheDocument();
      expect(within(clan1).getByRole("button", { name: /ver mais/i })).toBeInTheDocument();
    });

    it("não mostra o botão 'Ver mais' quando o clã tem 5 coaches ou menos", async () => {
      vi.mocked(fetchCoachClas).mockResolvedValue(buildSeisCoachesDoClan1().slice(0, 5));

      render(<CoachesPorCla />);

      const clan1 = await screen.findByTestId("clan-section-CLÃ 1");
      expect(within(clan1).getByText("Coach 5")).toBeInTheDocument();
      expect(within(clan1).queryByRole("button", { name: /ver mais/i })).not.toBeInTheDocument();
    });

    it("clicar em 'Ver mais' revela o restante e troca para 'Ver menos', que recolhe de volta", async () => {
      vi.mocked(fetchCoachClas).mockResolvedValue(buildSeisCoachesDoClan1());
      const user = userEvent.setup();

      render(<CoachesPorCla />);

      const clan1 = await screen.findByTestId("clan-section-CLÃ 1");
      await user.click(within(clan1).getByRole("button", { name: /ver mais/i }));

      expect(within(clan1).getByText("Coach 6")).toBeInTheDocument();
      const botaoVerMenos = within(clan1).getByRole("button", { name: /ver menos/i });
      expect(botaoVerMenos).toBeInTheDocument();

      await user.click(botaoVerMenos);

      expect(within(clan1).queryByText("Coach 6")).not.toBeInTheDocument();
      expect(within(clan1).getByRole("button", { name: /ver mais/i })).toBeInTheDocument();
    });

    it("busca por nome ignora o limite de 5 e mostra todos os resultados encontrados no clã", async () => {
      vi.mocked(fetchCoachClas).mockResolvedValue(buildSeisCoachesDoClan1());
      const user = userEvent.setup();

      render(<CoachesPorCla />);
      await screen.findByTestId("clan-section-CLÃ 1");

      await user.type(screen.getByLabelText(/buscar por nome/i), "Coach");

      const clan1 = screen.getByTestId("clan-section-CLÃ 1");
      expect(within(clan1).getByText("Coach 6")).toBeInTheDocument();
      expect(within(clan1).queryByRole("button", { name: /ver mais/i })).not.toBeInTheDocument();
    });
  });
});
