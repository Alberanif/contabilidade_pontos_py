import os
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

# Carrega .env da raiz do projeto
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

REQUIRED_VARS = [
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    "GSHEET_RECORDS_SPREADSHEET_ID",
    "GSHEET_RECORDS_SHEET_NAME",
    "GSHEET_TOTALS_SPREADSHEET_ID",
    "GSHEET_TOTALS_SHEET_NAME",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
]


def _validate():
    missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
    if missing:
        raise ValueError(
            f"Variáveis de ambiente obrigatórias não configuradas: {', '.join(missing)}"
        )


_validate()

# Google Sheets
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
GSHEET_RECORDS_SPREADSHEET_ID = os.getenv("GSHEET_RECORDS_SPREADSHEET_ID")
GSHEET_RECORDS_SHEET_NAME = os.getenv("GSHEET_RECORDS_SHEET_NAME")
GSHEET_TOTALS_SPREADSHEET_ID = os.getenv("GSHEET_TOTALS_SPREADSHEET_ID")
GSHEET_TOTALS_SHEET_NAME = os.getenv("GSHEET_TOTALS_SHEET_NAME")

# Planilha oficial de desafios. É validada somente quando a etapa de desafios
# é executada, para não interromper as demais fontes de pontos.
GSHEET_DESAFIOS_SPREADSHEET_ID = os.getenv("GSHEET_DESAFIOS_SPREADSHEET_ID")
GSHEET_DESAFIOS_SHEET_NAME = os.getenv("GSHEET_DESAFIOS_SHEET_NAME")
POINTS_PER_DESAFIO_SUBMISSION = int(
    os.getenv("POINTS_PER_DESAFIO_SUBMISSION", "10")
)

# Pontuação individual do coach por desafio — separada do valor de clã acima
# (que continua alimentando só o crédito contínuo por token do clã). A partir
# do corte de vigência (DESAFIO_PERCENTUAL_CLAN_CORTE, definido abaixo), exige
# também aprovação manual na plataforma (revisao_status == "aprovado"),
# espelhando a mesma regra que a apuração por percentual do clã já aplica.
POINTS_PER_DESAFIO_SUBMISSION_COACH = int(
    os.getenv("POINTS_PER_DESAFIO_SUBMISSION_COACH", "100")
)

# Planilha de Registros Pro-bono (opcional — não interrompe startup se ausente)
GSHEET_RECORDS_PRO_BONO_SPREADSHEET_ID = os.getenv("GSHEET_RECORDS_PRO_BONO_SPREADSHEET_ID")
GSHEET_RECORDS_PRO_BONO_SHEET_NAME = os.getenv("GSHEET_RECORDS_PRO_BONO_SHEET_NAME")

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Pontuação — Coaching Individual
POINTS_PER_COACHING_INDIVIDUAL = int(os.getenv("POINTS_PER_COACHING_INDIVIDUAL", "30"))

# Pontuação — Coaching em grupo / Coaching em Empresa (lote de 5 = 30 pts)
BATCH_SIZE_GROUP = int(os.getenv("BATCH_SIZE_GROUP", "5"))
POINTS_PER_BATCH_GROUP = int(os.getenv("POINTS_PER_BATCH_GROUP", "30"))
POINTS_PER_RECORD_IN_BATCH = POINTS_PER_BATCH_GROUP // BATCH_SIZE_GROUP  # = 6
GROUP_MODALIDADES = [
    "Coaching em grupo",
    "Coaching em Empresa (contrato corporativo)",
]

# Coluna I: "Número de pessoas atendidas por você nesse contrato"
COL_PARTICIPANTES_GROUP = 8

# Coluna B: "Nome do Coach responsável pelo atendimento:"
COL_COACH = 1

# Pontuação — Pro-bono (10 pts por registro, imediato, sem fila/batch)
POINTS_PER_PRO_BONO = int(os.getenv("POINTS_PER_PRO_BONO", "10"))
COL_PRO_BONO_KEY = 10  # Coluna K = índice 10 (ID único na planilha Pro-bono)

# Backend
BACKEND_HOST = os.getenv("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))

# Ranking de coaches — apenas registros a partir desta data contam para pontuação individual
COL_DATE_PAYING   = 10  # Coluna K (índice 10) — data na planilha de clientes pagantes
COL_DATE_PRO_BONO = 9   # Coluna J (índice 9)  — data na planilha de pro-bono

# Groq LLM Agent (opcional)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0.0"))

# Desafios — Corte de vigência para apuração por percentual e aprovação manual
DESAFIO_PERCENTUAL_CLAN_CORTE = date(2026, 8, 1)
