import pytest

from tom import load_instance


@pytest.fixture(scope="session")
def instance():
    return load_instance()


@pytest.fixture(scope="session")
def optimum(instance):
    from tom import solve

    return solve(instance)
