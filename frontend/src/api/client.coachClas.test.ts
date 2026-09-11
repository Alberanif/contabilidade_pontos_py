import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createCoachCla,
  deleteCoachCla,
  fetchCoachClas,
  updateCoachCla,
} from "./client";

function mockFetchOnce(body: unknown, init?: { ok?: boolean; status?: number }) {
  const ok = init?.ok ?? true;
  const status = init?.status ?? (ok ? 200 : 500);
  const fetchMock = vi.fn().mockResolvedValue({
    ok,
    status,
    statusText: "",
    json: async () => body,
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("coach-clas client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetchCoachClas sem filtro chama GET /api/coach-clas", async () => {
    const registros = [{ coach_canonico: "Fulano", clan: "Fenix", categoria: "A" }];
    const fetchMock = mockFetchOnce(registros);

    const result = await fetchCoachClas();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/coach-clas");
    expect(options?.method ?? "GET").toBe("GET");
    expect(result).toEqual(registros);
  });

  it("fetchCoachClas com clan chama GET /api/coach-clas?clan=<clan>", async () => {
    const registros = [{ coach_canonico: "Fulano", clan: "Fenix", categoria: "A" }];
    const fetchMock = mockFetchOnce(registros);

    const result = await fetchCoachClas("Fenix");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/coach-clas?clan=Fenix");
    expect(result).toEqual(registros);
  });

  it("createCoachCla chama POST /api/coach-clas com o payload correto (caminho feliz)", async () => {
    const payload = { coach: "Fulano", clan: "Fenix", categoria: "A" };
    const criado = { coach_canonico: "Fulano", clan: "Fenix", categoria: "A" };
    const fetchMock = mockFetchOnce(criado);

    const result = await createCoachCla(payload);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/coach-clas");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual(payload);
    expect(result).toEqual(criado);
  });

  it("createCoachCla propaga erro 409 de forma distinguível (error.status)", async () => {
    mockFetchOnce(
      { detail: "Coach já pertence a outro clã" },
      { ok: false, status: 409 }
    );

    await expect(
      createCoachCla({ coach: "Fulano", clan: "Fenix", categoria: "A" })
    ).rejects.toMatchObject({
      status: 409,
      message: "Coach já pertence a outro clã",
    });
  });

  it("createCoachCla propaga outros erros sem status 409", async () => {
    mockFetchOnce({ detail: "Erro inesperado" }, { ok: false, status: 500 });

    await expect(
      createCoachCla({ coach: "Fulano", clan: "Fenix", categoria: "A" })
    ).rejects.toMatchObject({
      status: 500,
      message: "Erro inesperado",
    });
  });

  it("updateCoachCla chama PUT /api/coach-clas/{coach_canonico} com o payload correto", async () => {
    const atualizado = { coach_canonico: "Fulano", clan: "Hidra", categoria: "B" };
    const fetchMock = mockFetchOnce(atualizado);

    const result = await updateCoachCla("Fulano", { clan: "Hidra", categoria: "B" });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/coach-clas/Fulano");
    expect(options.method).toBe("PUT");
    expect(JSON.parse(options.body)).toEqual({ clan: "Hidra", categoria: "B" });
    expect(result).toEqual(atualizado);
  });

  it("deleteCoachCla chama DELETE /api/coach-clas/{coach_canonico}", async () => {
    const fetchMock = mockFetchOnce({});

    await deleteCoachCla("Fulano");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/coach-clas/Fulano");
    expect(options.method).toBe("DELETE");
  });
});
