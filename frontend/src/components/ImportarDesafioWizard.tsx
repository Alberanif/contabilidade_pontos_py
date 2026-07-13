import { useEffect, useState } from "react";
import {
  previewImportacaoDesafio,
  confirmarImportacaoDesafio,
  fetchDesafiosImportaveis,
  type ColumnMapping,
  type ImportConfig,
  type ImportPreviewResult,
  type Desafio,
} from "../api/client";

type WizardStep = "upload" | "config" | "preview";

// A resposta de /api/desafios inclui as colunas novas de importação (data_inicio,
// data_fim, pontos_por_participacao) mesmo que o tipo Desafio em client.ts não as
// declare — são só usadas para pré-preencher o formulário ao atualizar um desafio existente.
interface DesafioImportavel extends Desafio {
  data_inicio?: string;
  data_fim?: string;
  pontos_por_participacao?: number;
}

const CAMPOS_MAPEAMENTO: { key: keyof ColumnMapping; label: string }[] = [
  { key: "clan", label: "Clã" },
  { key: "nome", label: "Nome" },
  { key: "validado", label: "Validação (Sim/Não)" },
  { key: "submitted_at", label: "Data de submissão" },
  { key: "token", label: "Token" },
];

const MAPPING_VAZIO: ColumnMapping = {
  clan: "",
  nome: "",
  validado: "",
  submitted_at: "",
  token: "",
};

interface Props {
  onCancel: () => void;
  onImported: () => void;
}

export default function ImportarDesafioWizard({ onCancel, onImported }: Props) {
  const [step, setStep] = useState<WizardStep>("upload");

  // Upload state
  const [file, setFile] = useState<File | null>(null);
  const [headers, setHeaders] = useState<string[]>([]);
  const [mapping, setMapping] = useState<ColumnMapping>(MAPPING_VAZIO);

  // Config state
  const [desafiosImportaveis, setDesafiosImportaveis] = useState<DesafioImportavel[]>([]);
  const [modo, setModo] = useState<"novo" | "existente">("novo");
  const [desafioExistenteId, setDesafioExistenteId] = useState<number | "">("");
  const [nome, setNome] = useState("");
  const [dataInicio, setDataInicio] = useState("");
  const [dataFim, setDataFim] = useState("");
  const [pontosPorParticipacao, setPontosPorParticipacao] = useState<number>(10);

  // Preview state
  const [previewResult, setPreviewResult] = useState<ImportPreviewResult | null>(null);

  // UI state
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchDesafiosImportaveis()
      .then((data) => setDesafiosImportaveis(data as DesafioImportavel[]))
      .catch(() => {
        // dropdown de "atualizar existente" fica vazio se a busca falhar
      });
  }, []);

  const handleFileChange = (selected: File | null) => {
    setFile(selected);
    setHeaders([]);
    setMapping(MAPPING_VAZIO);
    setError("");
    if (!selected) return;

    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result ?? "");
      const firstLine = text.split(/\r?\n/, 1)[0] ?? "";
      const parsedHeaders = firstLine
        .split(",")
        .map((h) => h.trim().replace(/^"|"$/g, ""))
        .filter((h) => h.length > 0);
      setHeaders(parsedHeaders);
    };
    reader.onerror = () => setError("Não foi possível ler o arquivo CSV.");
    reader.readAsText(selected);
  };

  const mappingCompleto = CAMPOS_MAPEAMENTO.every((c) => mapping[c.key]);

  const handleSelecionarDesafioExistente = (id: number | "") => {
    setDesafioExistenteId(id);
    const desafio = desafiosImportaveis.find((d) => d.id === id);
    if (desafio) {
      setNome(desafio.nome);
      setDataInicio(desafio.data_inicio ?? "");
      setDataFim(desafio.data_fim ?? "");
      if (desafio.pontos_por_participacao != null) {
        setPontosPorParticipacao(desafio.pontos_por_participacao);
      }
    }
  };

  const configValido =
    (modo === "novo" ? nome.trim().length > 0 : desafioExistenteId !== "") &&
    dataInicio !== "" &&
    dataFim !== "" &&
    pontosPorParticipacao > 0;

  const buildConfig = (): ImportConfig => ({
    nome,
    ...(modo === "existente" && desafioExistenteId !== ""
      ? { desafio_id: Number(desafioExistenteId) }
      : {}),
    data_inicio: dataInicio,
    data_fim: dataFim,
    pontos_por_participacao: pontosPorParticipacao,
  });

  const handleGerarPreview = async () => {
    if (!file) return;
    try {
      setLoading(true);
      setError("");
      const result = await previewImportacaoDesafio(file, mapping, buildConfig());
      setPreviewResult(result);
      setStep("preview");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao gerar prévia da importação");
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmar = async () => {
    if (!file) return;
    try {
      setSubmitting(true);
      setError("");
      await confirmarImportacaoDesafio(file, mapping, buildConfig());
      onImported();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao confirmar importação");
    } finally {
      setSubmitting(false);
    }
  };

  const alertError = error && (
    <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
      {error}
    </div>
  );

  const stepLabel = { upload: "Upload", config: "Configuração", preview: "Prévia" }[step];

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center gap-3">
        <button onClick={onCancel} className="text-gray-500 hover:text-gray-700 text-sm">
          ← Desafios
        </button>
        <h2 className="text-2xl font-bold text-gray-800">Importar CSV</h2>
        <span className="text-sm text-gray-400">— {stepLabel}</span>
      </div>

      {alertError}

      {step === "upload" && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Arquivo CSV
            </label>
            <input
              type="file"
              accept=".csv"
              onChange={(e) => handleFileChange(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-gray-600 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100"
            />
          </div>

          {headers.length > 0 && (
            <div className="space-y-3">
              <p className="text-sm font-medium text-gray-700">Mapeamento de colunas</p>
              {CAMPOS_MAPEAMENTO.map((campo) => (
                <div key={campo.key} className="flex items-center gap-3">
                  <label className="w-48 text-sm text-gray-600">{campo.label}</label>
                  <select
                    value={mapping[campo.key]}
                    onChange={(e) =>
                      setMapping({ ...mapping, [campo.key]: e.target.value })
                    }
                    className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="">Selecione a coluna</option>
                    {headers.map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          )}

          <div className="flex gap-3">
            <button
              onClick={() => setStep("config")}
              disabled={!file || !mappingCompleto}
              className="bg-indigo-600 text-white px-6 py-2 rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Próximo
            </button>
            <button
              onClick={onCancel}
              className="bg-white text-gray-600 border border-gray-300 px-6 py-2 rounded-lg font-medium hover:bg-gray-50 transition-colors"
            >
              Cancelar
            </button>
          </div>
        </div>
      )}

      {step === "config" && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Desafio
            </label>
            <div className="flex rounded-lg border border-gray-300 overflow-hidden w-fit">
              <button
                type="button"
                onClick={() => setModo("novo")}
                className={`px-4 py-2 text-sm font-medium transition-colors ${
                  modo === "novo"
                    ? "bg-indigo-600 text-white"
                    : "bg-white text-gray-600 hover:bg-gray-50"
                }`}
              >
                Criar novo
              </button>
              <button
                type="button"
                onClick={() => setModo("existente")}
                className={`px-4 py-2 text-sm font-medium border-l border-gray-300 transition-colors ${
                  modo === "existente"
                    ? "bg-indigo-600 text-white"
                    : "bg-white text-gray-600 hover:bg-gray-50"
                }`}
              >
                Atualizar existente
              </button>
            </div>
          </div>

          {modo === "novo" ? (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Nome do desafio
              </label>
              <input
                type="text"
                value={nome}
                onChange={(e) => setNome(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="Ex: Desafio G"
              />
            </div>
          ) : (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Desafio existente
              </label>
              <select
                value={desafioExistenteId}
                onChange={(e) =>
                  handleSelecionarDesafioExistente(
                    e.target.value === "" ? "" : Number(e.target.value)
                  )
                }
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="">Selecione um desafio</option>
                {desafiosImportaveis.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.nome}
                  </option>
                ))}
              </select>
              {desafiosImportaveis.length === 0 && (
                <p className="mt-1 text-xs text-gray-500">
                  Nenhum desafio importado anteriormente disponível para atualização.
                </p>
              )}
            </div>
          )}

          <div className="flex gap-4">
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Início do período
              </label>
              <input
                type="date"
                value={dataInicio}
                onChange={(e) => setDataInicio(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Fim do período
              </label>
              <input
                type="date"
                value={dataFim}
                onChange={(e) => setDataFim(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Pontos por participação validada
            </label>
            <input
              type="number"
              min={1}
              value={pontosPorParticipacao}
              onChange={(e) => setPontosPorParticipacao(Number(e.target.value))}
              className="w-40 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div className="flex gap-3">
            <button
              onClick={handleGerarPreview}
              disabled={!configValido || loading}
              className="bg-indigo-600 text-white px-6 py-2 rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? "Calculando..." : "Gerar prévia"}
            </button>
            <button
              onClick={() => setStep("upload")}
              className="bg-white text-gray-600 border border-gray-300 px-6 py-2 rounded-lg font-medium hover:bg-gray-50 transition-colors"
            >
              Voltar
            </button>
            <button
              onClick={onCancel}
              className="bg-white text-gray-600 border border-gray-300 px-6 py-2 rounded-lg font-medium hover:bg-gray-50 transition-colors"
            >
              Cancelar
            </button>
          </div>
        </div>
      )}

      {step === "preview" && previewResult && (
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200 text-left text-gray-500">
                  <th className="py-3 px-4 font-medium">Clã</th>
                  <th className="py-3 px-4 font-medium text-center">Participações</th>
                  <th className="py-3 px-4 font-medium text-right">Pontos</th>
                </tr>
              </thead>
              <tbody>
                {Object.keys(previewResult.pontos_por_clan).length === 0 ? (
                  <tr>
                    <td colSpan={3} className="py-4 px-4 text-center text-gray-500">
                      Nenhuma participação validada encontrada para este período.
                    </td>
                  </tr>
                ) : (
                  Object.entries(previewResult.pontos_por_clan)
                    .sort(([a], [b]) => a.localeCompare(b))
                    .map(([clan, pontos]) => (
                      <tr key={clan} className="border-b border-gray-100 hover:bg-gray-50">
                        <td className="py-3 px-4 font-medium text-gray-700">{clan}</td>
                        <td className="py-3 px-4 text-center text-gray-600">
                          {previewResult.participacoes_por_clan[clan] ?? 0}
                        </td>
                        <td className="py-3 px-4 text-right font-bold text-indigo-600">
                          {pontos.toLocaleString("pt-BR")}
                        </td>
                      </tr>
                    ))
                )}
              </tbody>
            </table>
          </div>

          <p className="text-sm text-gray-500">
            Total de participações contabilizadas: {previewResult.total_linhas_contabilizadas}
          </p>

          {previewResult.avisos.length > 0 && (
            <div className="bg-yellow-50 border border-yellow-200 text-yellow-800 px-4 py-3 rounded-lg space-y-1">
              <p className="font-medium text-sm">Avisos</p>
              <ul className="list-disc list-inside text-sm">
                {previewResult.avisos.map((aviso, i) => (
                  <li key={i}>{aviso}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex gap-3">
            <button
              onClick={handleConfirmar}
              disabled={submitting}
              className="bg-indigo-600 text-white px-6 py-2 rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {submitting ? "Confirmando..." : "Confirmar importação"}
            </button>
            <button
              onClick={() => setStep("config")}
              className="bg-white text-gray-600 border border-gray-300 px-6 py-2 rounded-lg font-medium hover:bg-gray-50 transition-colors"
            >
              Voltar
            </button>
            <button
              onClick={onCancel}
              className="bg-white text-gray-600 border border-gray-300 px-6 py-2 rounded-lg font-medium hover:bg-gray-50 transition-colors"
            >
              Cancelar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
