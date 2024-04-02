import json
import importlib
from django.db import models
from django.utils import timezone
import sys
from typing import Callable, List


class Task(models.Model):
    """
    A model to represent a background task in the queue.
    """
    module_path = models.CharField(max_length=255)  # e.g., "myapp.tasks"
    function_name = models.CharField(max_length=255)  # e.g., "my_function"
    function_args = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)

    function_result = models.JSONField(default=dict, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    function_error = models.JSONField(default=dict, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self) -> str:
        started = self.started_at.strftime('%Y-%m-%d %H:%M:%S %Z') if self.started_at else None
        completed = self.completed_at.strftime('%Y-%m-%d %H:%M:%S %Z') if self.completed_at else None

        return (
            f"Task id={self.id}. "
            f"Module: {self.module_path}. "
            f"Function: {self.function_name}. "
            f"Started: {started}. "
            f"Completed: {completed}"
        )

    def run_task(self) -> None:
        module = importlib.import_module(self.module_path)
        function = getattr(module, self.function_name, None)

        if not function:
            self.function_error = "Function not found"
            self.failed_at = timezone.now()
            self.save()
            sys.stdout.write(f"Failed task: {self.id}\n")
            return

        args = self.function_args if isinstance(self.function_args, list) else []

        self.started_at = timezone.now()
        self.save()
        sys.stdout.write(f"Started task id={self.id}\n")

        self._execute(function, *args)

    def _execute(self, function: Callable, *args: List) -> None:
        """
        Execute the task's function and save the result or error.
        """
        try:
            sys.stdout.write(
                f'function = {function}\n'
                f'args = {args}\n'
            )
            result = function(*args)
            sys.stdout.write(f'result {result}\n')

            self.function_result = json.dumps(result, default=str)
            self.completed_at = timezone.now()
            sys.stdout.write(f"Completed task id={self.id}\n")

        except Exception as e:
            self.function_error = json.dumps(e, default=str)
            self.failed_at = timezone.now()
            sys.stdout.write(
                f"Failed task: {self.id}.\n"
                f"Reason: {self.function_error}\n"
            )
        finally:
            self.save()