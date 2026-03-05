from __future__ import annotations

from rest_framework import viewsets

from testapp.models import Task
from testapp.serializers import TaskSerializer


class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer
