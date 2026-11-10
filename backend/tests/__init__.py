
# A suíte usa TestClient sem credenciais; os testes de auth reativam a proteção.
import os as _os

_os.environ.setdefault("APP_AUTH_DISABLED", "true")
_os.environ.setdefault("SESSION_SECRET", "test-session-secret")
