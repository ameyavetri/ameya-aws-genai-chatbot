"""Base interface for ApplicationProvider."""

from typing import Protocol, Any


class ApplicationProvider(Protocol):
    """Protocol for fetching application data by ID."""

    def get_application(self, application_id: str) -> dict[str, Any] | None:
        """
        Fetch application by ID.

        Returns:
            DynamoDB item dict or None if not found.
        """
        ...
