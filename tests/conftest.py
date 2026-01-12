import os

def pytest_configure(config):
    config.addinivalue_line("markers", "integration: tests that require a running Postgres database")

    # Only set a default DATABASE_URL if integration tests are requested
    if config.getoption("-m") and "integration" in config.getoption("-m"):
        os.environ.setdefault(
            "DATABASE_URL",
            "postgresql+asyncpg://inboxsherpa:inboxsherpa@localhost:5432/inboxsherpa",
        )
