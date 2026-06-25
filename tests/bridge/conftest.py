"""Shared fixtures for bridge characterization tests (TASK-008).

Mocks GCP credentials and Google Chat settings to avoid real API calls.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_gcp_credentials(monkeypatch):
    """Mock Google service account credentials for all bridge tests.

    Patches from_service_account_file at each usage site.
    """
    fake_creds = MagicMock()
    monkeypatch.setattr(
        "app.bridge.google_chat.worker.service_account.Credentials.from_service_account_file",
        MagicMock(return_value=fake_creds),
    )
    monkeypatch.setattr(
        "app.bridge.google_chat.chat_client.service_account.Credentials.from_service_account_file",
        MagicMock(return_value=fake_creds),
    )
    monkeypatch.setattr(
        "app.bridge.google_chat.media_downloader.service_account.Credentials.from_service_account_file",
        MagicMock(return_value=fake_creds),
    )
    monkeypatch.setattr(
        "app.bridge.google_chat.pubsub_subscriber.service_account.Credentials.from_service_account_file",
        MagicMock(return_value=fake_creds),
    )
    return fake_creds
