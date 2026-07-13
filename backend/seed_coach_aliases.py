"""Script de migração única: popula pontos_ultimate_coach_aliases com o
levantamento de duplicatas feito em 2026-07-13 e roda o reprocessamento uma
vez. Ver docs/superpowers/specs/2026-07-13-coach-identity-aliases-design.md.

Uso: python seed_coach_aliases.py  (a partir de backend/, com venv ativo)
"""
import supabase_client
from routers.contabilidade import reprocessar_coaches

# (alias observado, nome canônico) — 22 grupos de duplicata confirmados:
# 18 triviais (case/acento/espaço) + 4 semânticos (Camilla, Vini/Vinicius,
# Tati/Tatiane, Solamita) confirmados nesta conversa. Backlog de ~17 pares
# adicionais (nome curto vs. completo) fica documentado na spec, para o
# usuário adicionar aqui quando confirmar cada um.
SEED = [
    ("ALEXSANDRE NAVES", "Alexsandre Naves"),
    ("Cassia Fajardo", "Cássia Fajardo"),
    ("clarissa Boeira", "Clarissa Boeira"),
    ("Claudete M Silva", "Claudete Maria da Silva"),
    ("Claudete m Silva", "Claudete Maria da Silva"),
    ("claudete m silva", "Claudete Maria da Silva"),
    ("Claudete M da Silva", "Claudete Maria da Silva"),
    ("DAMARIS ALFREDO SILVA DE OLIVEIRA", "Damaris Alfredo Silva de Oliveira"),
    ("FLAVIA GODOI", "Flavia Godoi"),
    ("Herverton Ferreira de Souza Sobrinho", "Hérverton Ferreira de Souza Sobrinho"),
    ("IVAN PEREIRA VIEIRA", "Ivan Pereira Vieira"),
    ("JOSE GEORGE C PEREIRA JUNIOR", "Jose George Canuto Pereira Junior"),
    ("Jose George C Pereira Junior", "Jose George Canuto Pereira Junior"),
    ("Jose George C. Pereira Junior", "Jose George Canuto Pereira Junior"),
    ("KARLLA  ANDRADE", "Karlla Andrade"),
    ("KARLLA ANDRADE", "Karlla Andrade"),
    ("KARLLA ANDADE", "Karlla Andrade"),
    ("KATIA APARECIDA DOS SANTOS", "Kátia Aparecida dos Santos"),
    ("KATIA APARECIDA DOS SANTOSQ", "Kátia Aparecida dos Santos"),
    ("MARIA BERNADETE LIMA DE OLIVEIRA", "Maria Bernadete Lima de Oliveira"),
    ("Patricia Pereira da Silva", "Patrícia Pereira da Silva"),
    ("pAULA pETROLI pIEROZZI", "Paula Petroli Pierozzi"),
    ("RAPHA FREITAS", "Rapha Freitas"),
    ("victor lucena", "Victor Lucena"),
    ("Vinicius Gonçalves Missiaggia", "Vinícius Gonçalves Missiaggia"),
    ("Wagner mendes faria", "Wagner Mendes Faria"),
    ("Camilla C Rentroia", "Camilla Crivelaro Rentroia"),
    ("Camilla Rentroia", "Camilla Crivelaro Rentroia"),
    ("Vini Marini", "Vinicius Marini"),
    ("Tati Pellicel", "Tatiane Pellicel"),
    ("solamita dos santos mariano", "Solamita dos Santos Mariano Rovarotto"),
    ("solamita dos santos mariano rovarotto", "Solamita dos Santos Mariano Rovarotto"),
]


def main():
    for alias, canonico in SEED:
        supabase_client.insert_coach_alias(alias, canonico)
    print(f"{len(SEED)} aliases inseridos.")

    resultado = reprocessar_coaches()
    print(f"registros_atualizados={resultado.registros_atualizados}")
    print(f"coaches_afetados={resultado.coaches_afetados}")
    print(f"totais_recalculados={resultado.totais_recalculados}")
    if resultado.avisos:
        print(f"AVISOS: {resultado.avisos}")


if __name__ == "__main__":
    main()
