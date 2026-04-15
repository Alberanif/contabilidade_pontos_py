interface ClanCardProps {
  clan: string;
  totalPontos: number;
}

export default function ClanCard({ clan, totalPontos }: ClanCardProps) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 flex flex-col items-center gap-2">
      <span className="text-sm font-medium text-gray-500 uppercase tracking-wide">
        {clan}
      </span>
      <span className="text-3xl font-bold text-indigo-700">
        {totalPontos.toLocaleString("pt-BR")}
      </span>
      <span className="text-xs text-gray-400">pontos</span>
    </div>
  );
}
