# src/core/__init__.py
from .clius_monitor import main as clius_monitor_main
from .task_assignment import main as task_assignment_main
from .staff_status_sync import main as staff_status_sync_main
from .medical_data_inserter import main as medical_data_inserter_main

__all__ = ['clius_monitor_main', 'task_assignment_main', 'staff_status_sync_main', 'medical_data_inserter_main']