# auth_middleware.py
import os
from dotenv import load_dotenv
import jwt
from jwt import PyJWKClient
from functools import wraps
from flask import request, jsonify, g
load_dotenv()
SUPABASE_URL = os.environ["SUPABASE_URL"]

# Fetch public key tự động — cache lại, không gọi mỗi request
_jwks_client = PyJWKClient(
    f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json",
    cache_keys=True  # ✅ cache public key, chỉ fetch lại khi key rotate
)

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({"error": "Missing token"}), 401
        token = header.split(" ", 1)[1]
        try:
            signing_key = _jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256", "HS256"],
                audience="authenticated",
            )
            g.uid   = payload["sub"]
            g.email = payload.get("email", "")
            g.role  = payload.get("role", "authenticated")
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated


def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if g.role != "admin":
            return jsonify({"error": "Forbidden"}), 403
        return f(*args, **kwargs)
    return decorated