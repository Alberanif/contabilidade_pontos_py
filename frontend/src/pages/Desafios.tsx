import { useEffect, useState } from "react";
import {
  fetchRanking,
  atualizarPlanilha,
  fetchDesafios,
  createDesafio,
  updateDesafio,
  deleteDesafio,
  fetchDesafioRegistros,
  type RankingEntry,
  type Desafio,
  type DesafioRegistro,
} from "../api/client";
import ImportarDesafioWizard from "../components/ImportarDesafioWizard";

function formatDate(dateStr: string): string {
  if (!dateStr) return "-";
  const parts = dateStr.substring(0, 10).split("-");
  if (parts.length !== 3) return dateStr;
  const [year, month, day] = parts;
  return `${day}/${month}/${year}`;
}

function formatPeriodo(d: Desafio): string {
  if (d.data_inicio && d.data_fim) {
    return `${formatDate(d.data_inicio)} - ${formatDate(d.data_fim)}`;
  }
  return formatDate(d.data);
}

type Mode = "list" | "form" | "detail" | "import";

interface RegistroForm {
  clan: string;
  pontos: string;
}

export default function Desafios() {
  const [mode, setMode] = useState<Mode>("list");
  const [desafios, setDesafios] = useState<Desafio[]>([]);
  const [selectedDesafio, setSelectedDesafio] = useState<Desafio | null>(null);
  const [registros, setRegistros] = useState<DesafioRegistro[]>([]);
  const [ranking, setRanking] = useState<RankingEntry[]>([]);

  // Form state
  const [editingDesafio, setEditingDesafio] = useState<Desafio | null>(null);
  const [formNome, setFormNome] = useState("");
  const [formContabilizar, setFormContabilizar] = useState(true);
  const [formDataInicio, setFormDataInicio] = useState("");
  const [formDataFim, setFormDataFim] = useState("");
  const [formRegistros, setFormRegistros] = useState<RegistroForm[]>([]);

  // UI state
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [updatingSheet, setUpdatingSheet] = useState(false);
  const [sheetMessage, setSheetMessage] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const loadDesafios = async () => {
    try {
      setLoading(true);
      const data = await fetchDesafios();
      setDesafios(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao carregar desafios");
    } finally {
      setLoading(false);
    }
  };

  const loadRanking = async () => {
    try {
      const data = await fetchRanking();
      setRanking(data);
    } catch {
      // ranking é opcional
    }
  };

  const loadRegistros = async (desafioId: number) => {
    try {
      const data = await fetchDesafioRegistros(desafioId);
      setRegistros(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao carregar registros");
    }
  };

  useEffect(() => {
    loadDesafios();
    loadRanking();
  }, []);

  const handleAtualizarPlanilha = async () => {
    try {
      setUpdatingSheet(true);
      setSheetMessage("");
      setError("");
      const data = await atualizarPlanilha();
      setSheetMessage(data.mensagem);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao atualizar planilha");
    } finally {
      setUpdatingSheet(false);
    }
  };

  const openCreateForm = () => {
    setEditingDesafio(null);
    setFormNome("");
    setFormContabilizar(true);
    setFormDataInicio("");
    setFormDataFim("");
    setFormRegistros([]);
    setError("");
    setSuccess("");
    setMode("form");
  };

  const openEditForm = async (desafio: Desafio) => {
    setEditingDesafio(desafio);
    setFormNome(desafio.nome);
    setFormContabilizar(desafio.contabilizar_pontos);
    setFormDataInicio(desafio.data_inicio ?? desafio.data ?? "");
    setFormDataFim(desafio.data_fim ?? desafio.data ?? "");
    setError("");
    setSuccess("");
    try {
      const data = await fetchDesafioRegistros(desafio.id);
      setFormRegistros(data.map((r) => ({ clan: r.clan, pontos: String(r.total_pontos) })));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao carregar registros do desafio");
      setFormRegistros([]);
    }
    setMode("form");
  };

  const openDetail = async (desafio: Desafio) => {
    setSelectedDesafio(desafio);
    setError("");
    setSuccess("");
    await loadRegistros(desafio.id);
    setMode("detail");
  };

  const addRegistroRow = () => {
    setFormRegistros([...formRegistros, { clan: "", pontos: "0" }]);
  };

  const removeRegistroRow = (index: number) => {
    setFormRegistros(formRegistros.filter((_, i) => i !== index));
  };

  const updateRegistroRow = (
    index: number,
    field: keyof RegistroForm,
    value: string
  ) => {
    setFormRegistros(
      formRegistros.map((r, i) => (i === index ? { ...r, [field]: value } : r))
    );
  };

  const clanOptionsFor = (index: number) => {
    const chosenElsewhere = new Set(
      formRegistros.filter((_, i) => i !== index).map((r) => r.clan)
    );
    return ranking.filter((r) => !chosenElsewhere.has(r.clan));
  };

  const handleSaveDesafio = async () => {
    if (!formNome.trim()) {
      setError("O nome do desafio é obrigatório.");
      return;
    }
    if (!formDataInicio || !formDataFim) {
      setError("O período (data início e fim) é obrigatório.");
      return;
    }
    if (formDataFim < formDataInicio) {
      setError("A data fim deve ser maior ou igual à data início.");
      return;
    }
    if (formRegistros.some((r) => !r.clan || r.pontos.trim() === "")) {
      setError("Selecione o clã e informe a pontuação em todas as linhas.");
      return;
    }
    const clansInformados = formRegistros.map((r) => r.clan);
    if (new Set(clansInformados).size !== clansInformados.length) {
      setError("Um mesmo clã não pode aparecer duas vezes.");
      return;
    }
    try {
      setSubmitting(true);
      setError("");
      const registros = formRegistros.map((r) => ({
        clan: r.clan,
        pontos: Number(r.pontos),
      }));
      if (editingDesafio) {
        await updateDesafio(editingDesafio.id, {
          nome: formNome,
          contabilizar_pontos: formContabilizar,
          data_inicio: formDataInicio,
          data_fim: formDataFim,
          registros,
        });
        setSuccess("Desafio atualizado com sucesso.");
      } else {
        await createDesafio({
          nome: formNome,
          contabilizar_pontos: formContabilizar,
          data_inicio: formDataInicio,
          data_fim: formDataFim,
          registros,
        });
        setSuccess("Desafio criado com sucesso.");
      }
      await loadDesafios();
      setMode("list");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao salvar desafio");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteDesafio = async (desafio: Desafio) => {
    const msg = desafio.contabilizar_pontos
      ? `Excluir o desafio "${desafio.nome}"? Os pontos dos clãs serão descontados.`
      : `Excluir o desafio "${desafio.nome}"?`;
    if (!confirm(msg)) return;
    try {
      setError("");
      await deleteDesafio(desafio.id);
      setSuccess(`Desafio "${desafio.nome}" excluído.`);
      await loadDesafios();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao excluir desafio");
    }
  };

  // --- Shared elements ---

  const sheetBtn = (
    <button
      onClick={handleAtualizarPlanilha}
      disabled={updatingSheet}
      className="bg-green-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
    >
      {updatingSheet ? "Atualizando..." : "Atualizar Planilha"}
    </button>
  );

  const alertError = error && (
    <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
      {error}
    </div>
  );

  const alertSuccess = success && (
    <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg">
      {success}
    </div>
  );

  const alertSheet = sheetMessage && (
    <div className="bg-blue-50 border border-blue-200 text-blue-700 px-4 py-3 rounded-lg">
      {sheetMessage}
    </div>
  );

  // --- List mode ---
  if (mode === "list") {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-2xl font-bold text-gray-800">Desafios</h2>
          <div className="flex gap-3">
            {sheetBtn}
            <button
              onClick={() => {
                setError("");
                setSuccess("");
                setMode("import");
              }}
              className="bg-white text-indigo-600 border border-indigo-600 px-4 py-2 rounded-lg font-medium hover:bg-indigo-50 transition-colors"
            >
              Importar CSV
            </button>
            <button
              onClick={openCreateForm}
              className="bg-indigo-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-indigo-700 transition-colors"
            >
              Novo Desafio
            </button>
          </div>
        </div>

        {alertError}
        {alertSuccess}
        {alertSheet}

        {loading ? (
          <p className="text-gray-500">Carregando desafios...</p>
        ) : desafios.length === 0 ? (
          <p className="text-gray-500">
            Nenhum desafio cadastrado. Clique em "Novo Desafio" para começar.
          </p>
        ) : (
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200 text-left text-gray-500">
                  <th className="py-3 px-4 font-medium">Nome</th>
                  <th className="py-3 px-4 font-medium">Período</th>
                  <th className="py-3 px-4 font-medium text-center">Clãs registrados</th>
                  <th className="py-3 px-4 font-medium text-center">Pontuação</th>
                  <th className="py-3 px-4 font-medium text-right">Ações</th>
                </tr>
              </thead>
              <tbody>
                {desafios.map((d) => (
                  <tr
                    key={d.id}
                    className="border-b border-gray-100 hover:bg-gray-50"
                  >
                    <td className="py-3 px-4">
                      <button
                        onClick={() => openDetail(d)}
                        className="font-medium text-indigo-600 hover:underline text-left"
                      >
                        {d.nome}
                      </button>
                    </td>
                    <td className="py-3 px-4 text-gray-600">
                      {formatPeriodo(d)}
                    </td>
                    <td className="py-3 px-4 text-center text-gray-600">
                      {d.total_registros}
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-medium ${
                          d.contabilizar_pontos
                            ? "bg-green-100 text-green-700"
                            : "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {d.contabilizar_pontos ? "Registrar" : "Não Registrar"}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right space-x-3">
                      {d.origem !== "csv_import" && (
                        <button
                          onClick={() => openEditForm(d)}
                          className="text-indigo-600 hover:text-indigo-800 text-sm font-medium"
                        >
                          Editar
                        </button>
                      )}
                      <button
                        onClick={() => handleDeleteDesafio(d)}
                        className="text-red-600 hover:text-red-800 text-sm font-medium"
                      >
                        Excluir
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  }

  // --- Import mode (CSV wizard) ---
  if (mode === "import") {
    return (
      <ImportarDesafioWizard
        onCancel={() => setMode("list")}
        onImported={async () => {
          setSuccess("Desafio importado com sucesso.");
          await loadDesafios();
          setMode("list");
        }}
      />
    );
  }

  // --- Form mode (create / edit) ---
  if (mode === "form") {
    return (
      <div className="space-y-6 max-w-2xl">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setMode("list")}
            className="text-gray-500 hover:text-gray-700 text-sm"
          >
            ← Desafios
          </button>
          <h2 className="text-2xl font-bold text-gray-800">
            {editingDesafio ? "Editar Desafio" : "Novo Desafio"}
          </h2>
        </div>

        {alertError}

        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Nome do desafio
            </label>
            <input
              type="text"
              value={formNome}
              onChange={(e) => setFormNome(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="Ex: Semana de Treinos"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Data início
              </label>
              <input
                type="date"
                value={formDataInicio}
                onChange={(e) => setFormDataInicio(e.target.value)}
                required
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Data fim
              </label>
              <input
                type="date"
                value={formDataFim}
                onChange={(e) => setFormDataFim(e.target.value)}
                required
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Pontuação no ranking
            </label>
            <div className="flex rounded-lg border border-gray-300 overflow-hidden w-fit">
              <button
                type="button"
                onClick={() => setFormContabilizar(true)}
                className={`px-4 py-2 text-sm font-medium transition-colors ${
                  formContabilizar
                    ? "bg-indigo-600 text-white"
                    : "bg-white text-gray-600 hover:bg-gray-50"
                }`}
              >
                Registrar Pontos
              </button>
              <button
                type="button"
                onClick={() => setFormContabilizar(false)}
                className={`px-4 py-2 text-sm font-medium border-l border-gray-300 transition-colors ${
                  !formContabilizar
                    ? "bg-indigo-600 text-white"
                    : "bg-white text-gray-600 hover:bg-gray-50"
                }`}
              >
                Não Registrar Pontos
              </button>
            </div>
            <p className="mt-1 text-xs text-gray-500">
              {formContabilizar
                ? "Os pontos deste desafio serão somados ao total geral dos clãs."
                : "Os pontos ficam apenas para controle interno, sem afetar o ranking."}
            </p>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-sm font-medium text-gray-700">
                Clãs e pontuação
              </label>
              <button
                type="button"
                onClick={addRegistroRow}
                className="text-indigo-600 hover:text-indigo-800 text-sm font-medium"
              >
                + Adicionar clã
              </button>
            </div>
            {formRegistros.length === 0 ? (
              <p className="text-sm text-gray-400 italic">
                Nenhum clã adicionado.
              </p>
            ) : (
              <div className="space-y-2">
                {formRegistros.map((registro, i) => (
                  <div key={i} className="flex gap-2 items-center">
                    <select
                      value={registro.clan}
                      onChange={(e) =>
                        updateRegistroRow(i, "clan", e.target.value)
                      }
                      className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    >
                      <option value="">Selecione um clã</option>
                      {clanOptionsFor(i).map((r) => (
                        <option key={r.clan} value={r.clan}>
                          {r.clan}
                        </option>
                      ))}
                    </select>
                    <input
                      type="number"
                      min={0}
                      value={registro.pontos}
                      onChange={(e) =>
                        updateRegistroRow(i, "pontos", e.target.value)
                      }
                      className="w-32 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      placeholder="0"
                    />
                    <button
                      type="button"
                      onClick={() => removeRegistroRow(i)}
                      className="text-red-500 hover:text-red-700 px-2 text-sm"
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="flex gap-3">
          <button
            onClick={handleSaveDesafio}
            disabled={submitting}
            className="bg-indigo-600 text-white px-6 py-2 rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? "Salvando..." : "Salvar Desafio"}
          </button>
          <button
            onClick={() => setMode("list")}
            className="bg-white text-gray-600 border border-gray-300 px-6 py-2 rounded-lg font-medium hover:bg-gray-50 transition-colors"
          >
            Cancelar
          </button>
        </div>
      </div>
    );
  }

  // --- Detail mode (somente leitura) ---
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              setMode("list");
              setSelectedDesafio(null);
            }}
            className="text-gray-500 hover:text-gray-700 text-sm"
          >
            ← Desafios
          </button>
          <h2 className="text-2xl font-bold text-gray-800">
            {selectedDesafio?.nome}
          </h2>
          {selectedDesafio && (
            <span
              className={`px-2 py-0.5 rounded text-xs font-medium ${
                selectedDesafio.contabilizar_pontos
                  ? "bg-green-100 text-green-700"
                  : "bg-gray-100 text-gray-600"
              }`}
            >
              {selectedDesafio.contabilizar_pontos
                ? "Registrar Pontos"
                : "Não Registrar Pontos"}
            </span>
          )}
          {selectedDesafio && (
            <span className="text-sm text-gray-500">
              {formatPeriodo(selectedDesafio)}
            </span>
          )}
        </div>
        <div className="flex gap-3">
          {sheetBtn}
          {selectedDesafio && selectedDesafio.origem !== "csv_import" && (
            <button
              onClick={() => openEditForm(selectedDesafio)}
              className="bg-indigo-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-indigo-700 transition-colors"
            >
              Editar
            </button>
          )}
        </div>
      </div>

      {alertError}
      {alertSuccess}
      {alertSheet}

      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-2">
          Clãs registrados ({registros.length})
        </h3>
        {registros.length === 0 ? (
          <p className="text-gray-500 text-sm">
            Nenhum clã registrado neste desafio ainda.
          </p>
        ) : (
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200 text-left text-gray-500">
                  <th className="py-3 px-4 font-medium">Clã</th>
                  <th className="py-3 px-4 font-medium text-right">Pontos</th>
                </tr>
              </thead>
              <tbody>
                {registros.map((reg) => (
                  <tr
                    key={reg.id}
                    className="border-b border-gray-100 hover:bg-gray-50"
                  >
                    <td className="py-3 px-4 font-medium text-gray-700">
                      {reg.clan}
                    </td>
                    <td className="py-3 px-4 text-right font-bold text-indigo-600">
                      {reg.total_pontos.toLocaleString("pt-BR")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
