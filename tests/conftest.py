import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: PI Web API integration tests")
    config.addinivalue_line("markers", "e2e: end-to-end tests against running agent")
