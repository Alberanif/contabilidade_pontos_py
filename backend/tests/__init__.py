
# A suíte usa TestClient sem sessão (bypass: get_current_user devolve um admin
# fictício); test_session_auth.py reativa a proteção real.
import os as _os

_os.environ.setdefault("APP_AUTH_DISABLED", "true")
_os.environ.setdefault("SESSION_SECRET", "test-session-secret")
