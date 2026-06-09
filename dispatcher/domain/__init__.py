"""Domain layer: models, ports, and exceptions."""

from dispatcher.domain.exceptions import DomainError, InvalidStateTransition
from dispatcher.domain.models import (
    Assignment,
    Service,
    ServiceStatus,
    Task,
    TaskPriority,
    TaskStatus,
)
from dispatcher.domain.ports import (
    AssignmentRepository,
    Broker,
    ServiceRepository,
    TaskRepository,
)

__all__ = [
    "Assignment",
    "AssignmentRepository",
    "Broker",
    "DomainError",
    "InvalidStateTransition",
    "Service",
    "ServiceRepository",
    "ServiceStatus",
    "Task",
    "TaskPriority",
    "TaskRepository",
    "TaskStatus",
]
