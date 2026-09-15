// Filtros combináveis (coach, clã, status, período) exibidos dentro do
// detalhe de um desafio, sobre a lista de submissões desse desafio (issue
// #18/#21). Clã e status são aplicados no servidor (refazem o fetch); coach e
// período são client-side, sobre as submissões já carregadas — mesma lógica
// de `submissoesFiltradas` em `Desafios.tsx`. O filtro de "token" é uma busca
// direta (ver `TokenSearch` em `Desafios.tsx`), não uma lista filtrável,
// então não aparece aqui. O filtro de "desafio" é a própria navegação para
// este detalhe.

export interface DesafioFiltersValue {
  clan: string;
  status: string;
  dataInicio: string;
  dataFim: string;
  coach: string;
}

export interface StatusOption {
  value: string;
  label: string;
}

interface DesafioFiltersProps {
  value: DesafioFiltersValue;
  onChange: (value: DesafioFiltersValue) => void;
  statusOptions: StatusOption[];
}

const inputClass =
  "border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500";

export default function DesafioFilters({ value, onChange, statusOptions }: DesafioFiltersProps) {
  return (
    <div className="flex flex-wrap gap-4 items-end bg-white border border-gray-200 rounded-xl p-4">
      <div>
        <label htmlFor="filtro-coach" className="block text-xs font-medium text-gray-500 mb-1">
          Buscar coach
        </label>
        <input
          id="filtro-coach"
          type="text"
          value={value.coach}
          onChange={(e) => onChange({ ...value, coach: e.target.value })}
          placeholder="Nome do coach"
          className={`${inputClass} w-48`}
        />
      </div>

      <div>
        <label htmlFor="filtro-cla" className="block text-xs font-medium text-gray-500 mb-1">
          Clã
        </label>
        <input
          id="filtro-cla"
          type="text"
          value={value.clan}
          onChange={(e) => onChange({ ...value, clan: e.target.value })}
          placeholder="Filtrar por clã"
          className={inputClass}
        />
      </div>

      <div>
        <label htmlFor="filtro-status" className="block text-xs font-medium text-gray-500 mb-1">
          Status
        </label>
        <select
          id="filtro-status"
          value={value.status}
          onChange={(e) => onChange({ ...value, status: e.target.value })}
          className={inputClass}
        >
          <option value="">Todos</option>
          {statusOptions.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="filtro-data-inicio" className="block text-xs font-medium text-gray-500 mb-1">
          Enviado a partir de
        </label>
        <input
          id="filtro-data-inicio"
          type="date"
          value={value.dataInicio}
          onChange={(e) => onChange({ ...value, dataInicio: e.target.value })}
          className={inputClass}
        />
      </div>

      <div>
        <label htmlFor="filtro-data-fim" className="block text-xs font-medium text-gray-500 mb-1">
          Enviado até
        </label>
        <input
          id="filtro-data-fim"
          type="date"
          value={value.dataFim}
          onChange={(e) => onChange({ ...value, dataFim: e.target.value })}
          className={inputClass}
        />
      </div>

      {(value.coach || value.clan || value.status || value.dataInicio || value.dataFim) && (
        <button
          type="button"
          onClick={() => onChange({ coach: "", clan: "", status: "", dataInicio: "", dataFim: "" })}
          className="text-gray-500 hover:text-gray-700 text-sm"
        >
          Limpar filtros
        </button>
      )}
    </div>
  );
}
