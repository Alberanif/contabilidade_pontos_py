import { describe, it, expect, vi, beforeEach } from "vitest";
import { fetchClans, logout, login, setAuthEventHandlers } from "./client";

function jsonResponse(status: number, body?: unknown) {
  return new Response(body === undefined ? null : JSON.stringify(body), { status });
}

describe("camada de API - autenticacao", () => {
  const onUnauthorized = vi.fn();
  const onPasswordChangeRequired = vi.fn();

  beforeEach(() => {
    onUnauthorized.mockReset();
    onPasswordChangeRequired.mockReset();
    setAuthEventHandlers({ onUnauthorized, onPasswordChangeRequired });
  });

  it("envia credentials: include", async () => {
    const f = vi.fn().mockResolvedValue(jsonResponse(200, []));
    vi.stubGlobal("fetch", f);
    await fetchClans();
    expect(f.mock.calls[0][1]).toMatchObject({ credentials: "include" });
  });

  it("401 em rota comum dispara o tratamento global", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(401, { detail: "x" })));
    await expect(fetchClans()).rejects.toMatchObject({ status: 401 });
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("401 no login nao dispara o tratamento global", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(401, { detail: "x" })));
    await expect(login("a@b.c", "x")).rejects.toMatchObject({ status: 401 });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("403 troca_de_senha_obrigatoria dispara o tratamento global", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(403, { detail: "troca_de_senha_obrigatoria" }))
    );
    await expect(fetchClans()).rejects.toMatchObject({ status: 403 });
    expect(onPasswordChangeRequired).toHaveBeenCalledTimes(1);
  });

  it("403 de outro tipo nao dispara", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(403, { detail: "Acesso negado" })));
    await expect(fetchClans()).rejects.toMatchObject({ status: 403 });
    expect(onPasswordChangeRequired).not.toHaveBeenCalled();
  });

  it("resposta 204 resolve sem corpo", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(logout()).resolves.toBeUndefined();
  });
});
