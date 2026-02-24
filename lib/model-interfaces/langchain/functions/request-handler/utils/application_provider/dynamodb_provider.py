"""DynamoDB implementation of ApplicationProvider."""

import os
from typing import Any

import boto3
from aws_lambda_powertools import Logger
from botocore.exceptions import ClientError

logger = Logger()

TABLE_NAME = os.environ.get("APPLICATIONS_TABLE_NAME")
_dynamodb = None
_table = None


def _get_table():
    global _table, _dynamodb
    if _table is None and TABLE_NAME:
        _dynamodb = boto3.resource("dynamodb")
        _table = _dynamodb.Table(TABLE_NAME)
    return _table


class DynamoDBApplicationProvider:
    """Fetches applications from DynamoDB."""

    def get_application(self, application_id: str) -> dict[str, Any] | None:
        """Fetch application by ID from DynamoDB."""
        table = _get_table()
        if not table:
            logger.warning("APPLICATIONS_TABLE_NAME not set, cannot fetch application")
            return None
        try:
            response = table.get_item(Key={"Id": application_id})
            return response.get("Item")
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                return None
            logger.exception("Error fetching application", application_id=application_id)
            return None
