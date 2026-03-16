"""Cliente Supabase singleton."""

import os
from functools import lru_cache
from supabase import create_client, Client


@lru_cache()
def get_supabase_client() -> Client:
    """Retorna cliente Supabase com service role (backend-only)."""
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def get_supabase_anon() -> Client:
    """Retorna cliente Supabase com anon key (para operações RLS-aware)."""
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_ANON_KEY"]
    return create_client(url, key)
