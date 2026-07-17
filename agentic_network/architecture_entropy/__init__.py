"""Read-only Architecture Entropy Gate public API."""

from agentic_network.architecture_entropy.runtime import (
    STATUS_ARCHITECTURE_REVIEW_REQUIRED,
    STATUS_ENTROPY_OK,
    STATUS_ENTROPY_WARNING,
    STATUS_REFACTOR_RECOMMENDED,
    evaluate_architecture_entropy,
)

__all__ = [
    "STATUS_ARCHITECTURE_REVIEW_REQUIRED",
    "STATUS_ENTROPY_OK",
    "STATUS_ENTROPY_WARNING",
    "STATUS_REFACTOR_RECOMMENDED",
    "evaluate_architecture_entropy",
]
