import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

// `@testing-library/react` só registra a limpeza automática via `afterEach`
// quando esse hook já existe no escopo global — não habilitamos
// `test.globals` no vitest.config.ts (preferimos imports explícitos nos
// testes), então registramos a limpeza manualmente aqui.
afterEach(() => {
  cleanup();
});
