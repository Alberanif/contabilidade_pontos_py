import os
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
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0.0"))


