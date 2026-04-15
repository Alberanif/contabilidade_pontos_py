import { useEffect, useState } from "react";
import {
  fetchRegistros,
  deleteRegistro,
  fetchClans,
  type Registro,
  type ClanTotal,
} from "../api/client";
import RegistrosTable from "../components/RegistrosTable";

export default function Registros() {
  const [registros, setRegistros] = useState<Registro[]>([]);
  const [clans, setClans] = useState<ClanTotal[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [filterClan, setFilterClan] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const limit = 50;

  const load = async () => {
    try {
      setLoading(true);
      setError("");
      const [regData, clanData] = await Promise.all([
        fetchRegistros({ clan: filterClan || undefined, status: filterStatus || undefined, limit, offset }),
        fetchClans(),
      ]);
      setRegistros(regData.registros);
      setTotal(regData.total);
      setClans(clanData);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao carregar registros");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [offset, filterClan, filterStatus]);

  const handleDelete = async (id: number) => {
    try {
      await deleteRegistro(id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao excluir registro");
    }
  };

  const totalPages = Math.ceil(total / limit);
  const currentPage = Math.floor(offset / limit) + 1;

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold text-gray-800">
        Registros Contabilizados
      </h2>

      <div className="flex items-center gap-3 flex-wrap">
        <select
          value={filterClan}
          onChange={(e) => { setFilterClan(e.target.value); setOffset(0); }}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
        >
          <option value="">Todos os clãs</option>
          {clans.map((c) => (
            <option key={c.id} value={c.clan}>{c.clan}</option>
          ))}
        </select>
        <select
          value={filterStatus}
          onChange={(e) => { setFilterStatus(e.target.value); setOffset(0); }}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
        >
          <option value="">Todos os status</option>
          <option value="contabilizado">Contabilizado</option>
          <option value="pendente">Pendente</option>
        </select>
        <span className="text-sm text-gray-500">
          {total} registro{total !== 1 ? "s" : ""} encontrado{total !== 1 ? "s" : ""}
        </span>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-gray-500">Carregando...</p>
      ) : (
        <>
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
            <RegistrosTable
              registros={registros}
              onDelete={handleDelete}
            />
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2">
              <button
                onClick={() => setOffset(Math.max(0, offset - limit))}
                disabled={offset === 0}
                className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg disabled:opacity-40 hover:bg-gray-50"
              >
                Anterior
              </button>
              <span className="text-sm text-gray-600">
                Página {currentPage} de {totalPages}
              </span>
              <button
                onClick={() => setOffset(offset + limit)}
                disabled={currentPage >= totalPages}
                className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg disabled:opacity-40 hover:bg-gray-50"
              >
                Próxima
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
