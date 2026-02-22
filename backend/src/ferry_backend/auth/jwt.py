"""GitHub App JWT generation using RS256.

Generates a short-lived JWT for authenticating as a GitHub App.
Fresh JWT per webhook cycle -- do NOT cache across invocations.

See: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app
"""

import time

import jwt as pyjwt


def generate_app_jwt(app_id: str, private_key: str) -> str:
    """Generate a GitHub App JWT valid for ~9 minutes.

    Args:
        app_id: GitHub App Client ID (e.g., "Iv1.abc123").
        private_key: RSA private key in PEM format.

    Returns:
        Encoded JWT string (PyJWT 2.0+ returns str, not bytes).

    Raises:
        jwt.exceptions.PyJWTError: If the private key is invalid or malformed.
    """
    now = int(time.time())
    payload = {
        "iat": now - 60,  # Backdate 60s for clock drift tolerance
        "exp": now + 540,  # 9 minutes (buffer before 10-min GitHub max)
        "iss": app_id,
    }
    return pyjwt.encode(payload, private_key, algorithm="RS256")
