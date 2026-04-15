import type { Registro } from "../api/client";

interface Props {
  registros: Registro[];
  onDelete?: (id: number) => void;
  showDelete?: boolean;
}

function getSubmittedAt(raw_data: string): string {
  try {
    const data = JSON.parse(raw_data);
    return data["Submitted At"] || data["Submitted at"] || "";
  } catch {
    return "";
  }
}

export default function RegistrosTable({
  registros,
  onDelete,
  showDelete = true,
}: Props) {
  if (registros.length === 0) {
    return (
      <p className="text-gray-500 text-center py-8">
        Nenhum registro encontrado.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-gray-500">
            <th className="py-2 px-3 font-medium">ID</th>
            <th className="py-2 px-3 font-medium">Clan</th>
            <th className="py-2 px-3 font-medium">Modalidade</th>
            <th className="py-2 px-3 font-medium">Status</th>
            <th className="py-2 px-3 font-medium text-right">Pontos</th>
            <th className="py-2 px-3 font-medium">Submitted At</th>
            <th className="py-2 px-3 font-medium">Processado em</th>
            {showDelete && <th className="py-2 px-3 font-medium"></th>}
          </tr>
        </thead>
        <tbody>
          {registros.map((r) => {
            const submittedAt = getSubmittedAt(r.raw_data);
            const isPendente = r.status === "pendente";
            return (
              <tr
                key={r.id}
                className="border-b border-gray-100 hover:bg-gray-50"
              >
                <td className="py-2 px-3 text-gray-400">{r.id}</td>
                <td className="py-2 px-3 font-medium">{r.clan}</td>
                <td className="py-2 px-3">{r.modalidade}</td>
                <td className="py-2 px-3">
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                    isPendente
                      ? "bg-yellow-100 text-yellow-700"
                      : "bg-green-100 text-green-700"
                  }`}>
                    {isPendente ? "Pendente" : "Contabilizado"}
                  </span>
                </td>
                <td className="py-2 px-3 text-right font-semibold text-indigo-600">
                  {isPendente ? "—" : `+${r.pontos}`}
                </td>
                <td className="py-2 px-3 text-gray-500">
                  {submittedAt || "—"}
                </td>
                <td className="py-2 px-3 text-gray-500">
                  {new Date(r.processed_at).toLocaleString("pt-BR")}
                </td>
                {showDelete && onDelete && (
                  <td className="py-2 px-3">
                    <button
                      onClick={() => {
                        const msg = isPendente
                          ? `Excluir registro #${r.id}? Este registro está pendente e não tem pontos contabilizados.`
                          : `Excluir registro #${r.id}? Isso descontará ${r.pontos} pontos do clã ${r.clan}.`;
                        if (confirm(msg)) onDelete(r.id);
                      }}
                      className="text-red-500 hover:text-red-700 text-xs font-medium"
                    >
                      Excluir
                    </button>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
