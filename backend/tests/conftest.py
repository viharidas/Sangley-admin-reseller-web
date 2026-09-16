import os
import requests
import pytest
import re
from pathlib import Path


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")


@pytest.fixture(scope="session")
def base_url():
    if not BASE_URL:
        pytest.fail("REACT_APP_BACKEND_URL is not set")
    return BASE_URL.rstrip("/")


@pytest.fixture()
def api_client():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="session")
def admin_credentials():
    credentials_file = Path("/app/memory/test_credentials.md")
    text = credentials_file.read_text() if credentials_file.exists() else ""
    email_match = re.search(r"- Email:\s*(.+)", text)
    password_match = re.search(r"- Password:\s*(.+)", text)
    email = email_match.group(1).strip() if email_match else os.environ.get("ADMIN_EMAIL")
    password = password_match.group(1).strip() if password_match else os.environ.get("ADMIN_PASSWORD")
    if not email or not password:
        pytest.fail("Admin credentials missing in /app/memory/test_credentials.md or environment")
    return {"email": email, "password": password}
