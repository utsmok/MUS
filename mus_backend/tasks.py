from django.db import transaction
from django.utils import timezone
from .models import Task
import time
import sys
import importlib
from typing import List, Optional


class TaskManager:
    """
    Manages task queue operations: adding, fetching, and processing tasks.
    """

    @staticmethod
    def add_task(
            module_path: str, function_name: str, function_args: Optional[List] = None
    ) -> Task:
        """
        Add a new task to the queue.
        :param module_path:  e.g., "myapp.tasks"
        :param function_name:  e.g., "my_function"
        :param function_args:  e.g., [1, 2, 3] or None
        """
        module = importlib.import_module(module_path)
        if not hasattr(module, function_name):
            raise ValueError(f"Function {function_name} not found in module {module_path}.")

        function_args = function_args or []
        if not isinstance(function_args, list):
            raise ValueError(
                f"Function {function_name} function_args must be None or a list. "
                f"Got type '{type(function_args)}' instead."
            )

        return Task.objects.create(
            module_path=module_path, function_name=function_name, function_args=function_args
        )

    @staticmethod
    @transaction.atomic
    def get_next_task() -> Task:
        """
        Atomically select and lock the next available task in the queue.
        """
        return (
            Task.objects
            .filter(started_at__isnull=True)
            .select_for_update(skip_locked=True)
            .first()
        )


class Worker:
    """
    Background worker that continuously fetches and processes tasks.
    """

    @staticmethod
    def run() -> None:
        """
        Start the worker loop.
        """
        sys.stdout.write("Started worker 🏗️\n")
        while True:
            task = TaskManager.get_next_task()
            if not task:
                sleep_seconds = 5
                current_time = timezone.now().strftime('%Y-%m-%d %H:%M:%S %Z')
                sys.stdout.write(
                    f"{current_time}: No tasks in the queue. Sleeping for {sleep_seconds} seconds 💤\n"
                )
                time.sleep(sleep_seconds)  # We reduce DB load by sleeping. I'd reduce this wait to 1 second in prod.
                continue
            task.run_task()


if __name__ == "__main__":
    Worker.run()

