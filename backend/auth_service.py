import os

from dotenv import load_dotenv
from supabase import create_client, Client


load_dotenv()


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")


if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL is missing.")

if not SUPABASE_ANON_KEY:
    raise RuntimeError("SUPABASE_ANON_KEY is missing.")


# Auth client
auth_client: Client = create_client(
    SUPABASE_URL,
    SUPABASE_ANON_KEY
)


def signup(email: str, password: str, full_name: str, phone: str = ""):
    """
    Create a new applicant using Supabase Auth.
    """

    response = auth_client.auth.sign_up({
        "email": email,
        "password": password,
        "options": {
            "data": {
                "full_name": full_name,
                "phone": phone
            }
        }
    })

    return response


def login(email: str, password: str):
    """
    Authenticate an applicant using Supabase Auth.
    """

    response = auth_client.auth.sign_in_with_password({
        "email": email,
        "password": password
    })

    return response


def logout():
    """
    Sign out the current Supabase Auth session.
    """

    return auth_client.auth.sign_out()