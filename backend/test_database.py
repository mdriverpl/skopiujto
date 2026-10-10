import pytest

from backend import database


@pytest.mark.parametrize('url', ['', 'sqlite:///data/documents.sqlite3'])
def test_database_requires_postgresql(url):
    with pytest.raises(ValueError, match='DATABASE_URL'):
        with database.connect(url):
            pytest.fail('Unsupported database connection was accepted')
