from __future__ import annotations

from rest_framework import serializers

from testapp.models import Task


class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ["id", "title", "done", "created"]
        read_only_fields = ["id", "created"]
