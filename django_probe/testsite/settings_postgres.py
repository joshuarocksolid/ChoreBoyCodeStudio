"""Django settings for PostgreSQL probes on ChoreBoy."""
from __future__ import annotations

from testsite.settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django_pg8000",
        "NAME": "django_probe",
        "USER": "postgres",
        "PASSWORD": "true",
        "HOST": "localhost",
        "PORT": 5432,
        "CONN_HEALTH_CHECKS": True,
        "CONN_MAX_AGE": None,
    }
}
