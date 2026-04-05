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

# Backend
BACKEND_HOST = os.getenv("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
