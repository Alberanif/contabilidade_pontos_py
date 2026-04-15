import { useEffect, useState } from "react";
import {
  fetchRanking,
  atualizarPlanilha,
  fetchDesafios,
  createDesafio,
  updateDesafio,
  deleteDesafio,
  fetchDesafioRegistros,
  createDesafioRegistro,
  deleteDesafioRegistro,
  type RankingEntry,
  type Desafio,
  type DesafioRegistro,
} from "../api/client";

type Mode = "list" | "form" | "detail";

interface CampoForm {
  id?: number;
  nome: string;
  tipo: "texto" | "pontuacao";
  ordem: number;
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
  const [formCampos, setFormCampos] = useState<CampoForm[]>([]);

  // Register form state
  const [showRegisterForm, setShowRegisterForm] = useState(false);
  const [registerClan, setRegisterClan] = useState("");
  const [registerValores, setRegisterValores] = useState<Record<string, string>>({});

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
    setFormCampos([]);
    setError("");
    setSuccess("");
    setMode("form");
  };

  const openEditForm = (desafio: Desafio) => {
    setEditingDesafio(desafio);
    setFormNome(desafio.nome);
    setFormContabilizar(desafio.contabilizar_pontos);
    setFormCampos(
      desafio.campos.map((c) => ({
        id: c.id,
        nome: c.nome,
        tipo: c.tipo,
        ordem: c.ordem,
      }))
    );
    setError("");
    setSuccess("");
    setMode("form");
  };

  const openDetail = async (desafio: Desafio) => {
    setSelectedDesafio(desafio);
    setShowRegisterForm(false);
    setError("");
    setSuccess("");
    await loadRegistros(desafio.id);
    setMode("detail");
  };

  const addCampo = () => {
    setFormCampos([
      ...formCampos,
      { nome: "", tipo: "texto", ordem: formCampos.length },
    ]);
  };

  const removeCampo = (index: number) => {
    setFormCampos(formCampos.filter((_, i) => i !== index));
  };

  const updateCampoField = (
    index: number,
    field: keyof CampoForm,
    value: string | number
  ) => {
    setFormCampos(
      formCampos.map((c, i) => (i === index ? { ...c, [field]: value } : c))
    );
  };

  const handleSaveDesafio = async () => {
    if (!formNome.trim()) {
      setError("O nome do desafio é obrigatório.");
      return;
    }
    try {
      setSubmitting(true);
      setError("");
      const campos = formCampos.map((c, i) => ({
        nome: c.nome,
        tipo: c.tipo,
        ordem: i,
      }));
      if (editingDesafio) {
        await updateDesafio(editingDesafio.id, {
          nome: formNome,
          contabilizar_pontos: formContabilizar,
          campos,
        });
        setSuccess("Desafio atualizado com sucesso.");
      } else {
        await createDesafio({
          nome: formNome,
          contabilizar_pontos: formContabilizar,
          campos,
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

  const handleDeleteRegistro = async (registro: DesafioRegistro) => {
    if (!confirm(`Remover o registro do clã "${registro.clan}"?`)) return;
    try {
      setError("");
      await deleteDesafioRegistro(selectedDesafio!.id, registro.id);
      setSuccess(`Registro do clã "${registro.clan}" removido.`);
      await loadRegistros(selectedDesafio!.id);
      await loadDesafios();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao excluir registro");
    }
  };

  const registeredClans = new Set(registros.map((r) => r.clan));
  const availableClans = ranking.filter((r) => !registeredClans.has(r.clan));

  const handleRegister = async () => {
    if (!registerClan) {
      setError("Selecione um clã.");
      return;
    }
    try {
      setSubmitting(true);
      setError("");
      await createDesafioRegistro(selectedDesafio!.id, {
        clan: registerClan,
        valores: registerValores,
      });
      setSuccess(`Pontos do clã "${registerClan}" registrados.`);
      setShowRegisterForm(false);
      setRegisterClan("");
      setRegisterValores({});
      await loadRegistros(selectedDesafio!.id);
      await loadDesafios();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao registrar pontos");
    } finally {
      setSubmitting(false);
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
                  <th className="py-3 px-4 font-medium text-center">Campos</th>
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
                    <td className="py-3 px-4 text-center text-gray-600">
                      {d.campos.length}
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
                      <button
                        onClick={() => openEditForm(d)}
                        className="text-indigo-600 hover:text-indigo-800 text-sm font-medium"
                      >
                        Editar
                      </button>
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
                Campos
              </label>
              <button
                type="button"
                onClick={addCampo}
                className="text-indigo-600 hover:text-indigo-800 text-sm font-medium"
              >
                + Adicionar campo
              </button>
            </div>
            {formCampos.length === 0 ? (
              <p className="text-sm text-gray-400 italic">
                Nenhum campo adicionado.
              </p>
            ) : (
              <div className="space-y-2">
                {formCampos.map((campo, i) => (
                  <div key={i} className="flex gap-2 items-center">
                    <input
                      type="text"
                      value={campo.nome}
                      onChange={(e) =>
                        updateCampoField(i, "nome", e.target.value)
                      }
                      className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      placeholder="Nome do campo"
                    />
                    <select
                      value={campo.tipo}
                      onChange={(e) =>
                        updateCampoField(i, "tipo", e.target.value)
                      }
                      className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    >
                      <option value="texto">Texto</option>
                      <option value="pontuacao">Pontuação</option>
                    </select>
                    <button
                      type="button"
                      onClick={() => removeCampo(i)}
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

  // --- Detail mode ---
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
        </div>
        <div className="flex gap-3">
          {sheetBtn}
          {availableClans.length > 0 && !showRegisterForm && (
            <button
              onClick={() => {
                setShowRegisterForm(true);
                setError("");
              }}
              className="bg-indigo-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-indigo-700 transition-colors"
            >
              Registrar Pontos
            </button>
          )}
        </div>
      </div>

      {alertError}
      {alertSuccess}
      {alertSheet}

      {selectedDesafio && selectedDesafio.campos.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <h3 className="text-sm font-semibold text-gray-600 mb-2">
            Campos do desafio
          </h3>
          <div className="flex flex-wrap gap-2">
            {selectedDesafio.campos.map((c) => (
              <span
                key={c.id}
                className="px-3 py-1 rounded-full border text-xs font-medium bg-gray-50 text-gray-700"
              >
                {c.nome}
                <span
                  className={`ml-1.5 ${
                    c.tipo === "pontuacao"
                      ? "text-indigo-500"
                      : "text-gray-400"
                  }`}
                >
                  ({c.tipo === "pontuacao" ? "pontuação" : "texto"})
                </span>
              </span>
            ))}
          </div>
        </div>
      )}

      {showRegisterForm && selectedDesafio && (
        <div className="bg-white rounded-xl border border-indigo-200 p-5 space-y-4">
          <h3 className="text-sm font-semibold text-gray-700">
            Registrar pontos para um clã
          </h3>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Clã
            </label>
            <select
              value={registerClan}
              onChange={(e) => setRegisterClan(e.target.value)}
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">Selecione um clã</option>
              {availableClans.map((r) => (
                <option key={r.clan} value={r.clan}>
                  {r.clan}
                </option>
              ))}
            </select>
          </div>

          {selectedDesafio.campos.map((campo) => (
            <div key={campo.id}>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {campo.nome}
                {campo.tipo === "pontuacao" && (
                  <span className="ml-1 text-xs text-indigo-500">
                    (pontuação)
                  </span>
                )}
              </label>
              {campo.tipo === "pontuacao" ? (
                <input
                  type="number"
                  min={0}
                  value={registerValores[String(campo.id)] ?? ""}
                  onChange={(e) =>
                    setRegisterValores({
                      ...registerValores,
                      [String(campo.id)]: e.target.value,
                    })
                  }
                  className="w-40 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="0"
                />
              ) : (
                <input
                  type="text"
                  value={registerValores[String(campo.id)] ?? ""}
                  onChange={(e) =>
                    setRegisterValores({
                      ...registerValores,
                      [String(campo.id)]: e.target.value,
                    })
                  }
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              )}
            </div>
          ))}

          <div className="flex gap-3">
            <button
              onClick={handleRegister}
              disabled={submitting}
              className="bg-indigo-600 text-white px-5 py-2 rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {submitting ? "Salvando..." : "Salvar"}
            </button>
            <button
              onClick={() => {
                setShowRegisterForm(false);
                setRegisterClan("");
                setRegisterValores({});
                setError("");
              }}
              className="bg-white text-gray-600 border border-gray-300 px-5 py-2 rounded-lg font-medium hover:bg-gray-50 transition-colors"
            >
              Cancelar
            </button>
          </div>
        </div>
      )}

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
                  {selectedDesafio?.campos.map((c) => (
                    <th key={c.id} className="py-3 px-4 font-medium">
                      {c.nome}
                    </th>
                  ))}
                  <th className="py-3 px-4 font-medium text-right">
                    Total pontos
                  </th>
                  <th className="py-3 px-4 font-medium text-right">Ação</th>
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
                    {selectedDesafio?.campos.map((c) => (
                      <td key={c.id} className="py-3 px-4 text-gray-600">
                        {String(reg.valores[String(c.id)] ?? "-")}
                      </td>
                    ))}
                    <td className="py-3 px-4 text-right font-bold text-indigo-600">
                      {reg.total_pontos.toLocaleString("pt-BR")}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button
                        onClick={() => handleDeleteRegistro(reg)}
                        className="text-red-600 hover:text-red-800 text-sm font-medium"
                      >
                        Remover
                      </button>
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
