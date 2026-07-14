import asyncio
import os
import pytest
import respx
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_http():
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
def db():
    from backend.db.client import db as real_db
    return real_db
