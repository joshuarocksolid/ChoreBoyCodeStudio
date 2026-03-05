from __future__ import annotations

from testsite.settings import *  # noqa: F401,F403

INSTALLED_APPS = INSTALLED_APPS + [  # noqa: F405
    "rest_framework",
]

ROOT_URLCONF = "testsite.urls_drf"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "UNAUTHENTICATED_USER": None,
}
