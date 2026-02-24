"""Application provider for fetching application config by ID."""

from .base import ApplicationProvider
from .dynamodb_provider import DynamoDBApplicationProvider

_provider: ApplicationProvider | None = None


def get_application_provider() -> ApplicationProvider:
    """Return the application provider instance."""
    global _provider
    if _provider is None:
        _provider = DynamoDBApplicationProvider()
    return _provider
