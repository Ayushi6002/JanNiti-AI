from functools import wraps

from flask import request, jsonify, g

from backend.supabase_client import get_supabase_user, supabase


def get_supabase_token():
    """
    Extract the Supabase access token from the Authorization header or query parameter.
    """
    auth_header = request.headers.get("Authorization", "")

    if auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1].strip()

    token_param = request.args.get("token")
    if token_param:
        return token_param.strip()

    return None


def get_supabase_current_user():
    """
    Validate the Supabase token and return the corresponding
    profile information. Auto-creates an applicant profile row
    if a legitimate authenticated Supabase user doesn't have one yet.
    """

    token = get_supabase_token()

    if not token:
        return None

    try:
        user = get_supabase_user(token)

        if not user:
            return None

        response = (
            supabase
            .table("profiles")
            .select("id, full_name, phone, role, created_at")
            .eq("id", user.id)
            .execute()
        )

        profile = response.data[0] if response.data else None

        if not profile:
            # Controlled auto-creation: default role strictly to 'applicant'
            metadata = getattr(user, "user_metadata", {}) or {}
            full_name = metadata.get("full_name") or metadata.get("name") or ""
            phone = metadata.get("phone") or None
            insert_res = (
                supabase
                .table("profiles")
                .insert({
                    "id": user.id,
                    "full_name": full_name,
                    "phone": phone,
                    "role": "applicant",
                })
                .execute()
            )
            profile = insert_res.data[0] if insert_res.data else {
                "id": user.id,
                "full_name": full_name,
                "phone": phone,
                "role": "applicant",
            }

        # Attach authenticated user email for consistency
        profile["email"] = getattr(user, "email", "") or ""

        return profile

    except Exception as exc:
        print("get_supabase_current_user error:", exc)
        return None


def require_supabase_role(required_role=None):
    """
    Require a valid Supabase user and optionally a specific profile role.
    """

    def decorator(fn):

        @wraps(fn)
        def wrapper(*args, **kwargs):

            user = get_supabase_current_user()

            if not user:
                return jsonify({
                    "error": "Authentication required"
                }), 401

            if required_role and user["role"] != required_role:
                return jsonify({
                    "error": f"{required_role.title()} role required"
                }), 403

            g.supabase_user = user

            return fn(*args, **kwargs)

        return wrapper

    return decorator

