from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from testapp.views_api import TaskViewSet

router = DefaultRouter()
router.register(r"tasks", TaskViewSet)

urlpatterns = [
    path("api/", include(router.urls)),
]
