"""Database connections with a common parameterized SQL interface."""
import re
import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

IntegrityError = psycopg.IntegrityError
# Preserve the old single-writer transaction semantics across PostgreSQL workers.
WRITE_LOCK = 1745026010

def columns(con, table):
    return con.columns(table)

class Row(dict):
    def __getitem__(self, key):
        return tuple(self.values())[key] if isinstance(key, int) else super().__getitem__(key)

def row_factory(cursor):
    factory = dict_row(cursor)
    return lambda values: Row(factory(values))

def postgres_parameters(query):
    # Replace placeholders only outside quoted SQL literals/identifiers.
    return re.sub(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|[?%]",
        lambda match: '%s' if match[0] == '?' else match[0].replace('%', '%%'), query)

class Connection:
    def __init__(self, raw, schema):
        self.raw = raw
        self.schema = schema

    def ensure_schema(self):
        self.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"')

    def execute(self, query, params=()):
        if params: query = postgres_parameters(query)
        params = tuple(int(value) if isinstance(value, bool) else value for value in params)
        return self.raw.cursor().execute(query, params) if params else self.raw.cursor().execute(query)

    def executescript(self, script):
        # Keep schema changes within this transaction.
        for query in script.split(';'):
            if query.strip(): self.execute(query)

    def begin_write(self):
        self.execute('SELECT pg_advisory_xact_lock(?)', (WRITE_LOCK,))

    def columns(self, table):
        if not re.fullmatch('[a-z_]+', table): raise ValueError('Invalid table name')
        return {row['column_name'] for row in self.execute(
            'SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=?', (table,))}

@contextmanager
def connect(url):
    if not url:
        raise ValueError('DATABASE_URL is required; configure a PostgreSQL connection in .env')
    if not url.startswith(('postgresql://', 'postgres://')):
        raise ValueError('DATABASE_URL must be a PostgreSQL connection URL')
    schema = os.getenv('DATABASE_SCHEMA', 'edokumenty')
    if not re.fullmatch('[a-z][a-z0-9_]{0,62}', schema):
        raise ValueError('DATABASE_SCHEMA must be a lowercase SQL identifier')
    raw = psycopg.connect(url, connect_timeout=10, cursor_factory=psycopg.ClientCursor, row_factory=row_factory)
    con = Connection(raw, schema=schema)
    try:
        con.execute(f'SET LOCAL search_path TO "{schema}"')
        con.execute("SET LOCAL lock_timeout = '15s'")
        con.execute("SET LOCAL statement_timeout = '60s'")
        yield con
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()
