import os

from dotenv import load_dotenv
from supabase import create_client, Client


# Load environment variables
load_dotenv()


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")


if not SUPABASE_URL:
    raise RuntimeError(
        "SUPABASE_URL is missing from environment variables."
    )

if not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError(
        "SUPABASE_SERVICE_ROLE_KEY is missing from environment variables."
    )


supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY
)
def get_supabase_user(access_token: str):
    """
    Validate a Supabase access token and return the authenticated user.
    """

    if not access_token:
        return None

    response = supabase.auth.get_user(access_token)

    return response.user