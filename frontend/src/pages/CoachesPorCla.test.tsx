import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CoachesPorCla from "./CoachesPorCla";
import { fetchCoachClas, type CoachCla } from "../api/client";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    fetchCoachClas: vi.fn(),
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

  it("shows no add/edit/move/remove affordances (read-only in this task)", async () => {
    vi.mocked(fetchCoachClas).mockResolvedValue([
      buildCoachCla({ coach_canonico: "Ana Albertim", clan: "CLÃ 1", categoria: "Ouro" }),
    ]);

    render(<CoachesPorCla />);
    await screen.findByText("Ana Albertim");

    for (const name of [/adicionar/i, /^editar$/i, /^excluir$/i, /^remover$/i, /^mover$/i, /^salvar$/i]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
  });
});
