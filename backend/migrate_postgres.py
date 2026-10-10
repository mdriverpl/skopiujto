"""Copy a SQLite snapshot into an empty PostgreSQL schema, then verify every row."""
import argparse
import base64
import hashlib
import importlib
import json
import os
import re
import sqlite3
import tempfile
from contextlib import contextmanager, closing
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values
from backend import database

ROOT = Path(__file__).resolve().parents[1]

def identifier(value):
    if not re.fullmatch('[a-z_][a-z0-9_]*', value): raise ValueError('Unsupported table or column name')
    return '"' + value + '"'

def tables(con):
    return [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]

def ordered_tables(con):
    remaining = set(tables(con))
    ordered = []
    while remaining:
        ready = sorted(table for table in remaining if not {
            row[2] for row in con.execute(f'PRAGMA foreign_key_list({identifier(table)})')
            if row[2] != table
        } & remaining)
        if not ready: raise ValueError('Unsupported circular table references')
        ordered.extend(ready)
        remaining.difference_update(ready)
    return ordered

def ordered_rows(con, table):
    rows = list(con.execute(f'SELECT * FROM {identifier(table)}'))
    if table != 'folders': return rows
    result, placed = [], set()
    while rows:
        ready = [row for row in rows if row['parent_id'] is None or row['parent_id'] in placed]
        if not ready: raise ValueError('Invalid folder tree')
        result.extend(ready)
        placed.update(row['id'] for row in ready)
        rows = [row for row in rows if row['id'] not in placed]
    return result

def fingerprint(rows):
    def binary(value):
        if isinstance(value, (bytes, memoryview)): return {'bytes': base64.b64encode(value).decode('ascii')}
        raise TypeError('Unsupported database value')
    return sorted(hashlib.sha256(json.dumps(dict(row), sort_keys=True, ensure_ascii=False,
        default=binary, separators=(',', ':')).encode()).digest() for row in rows)

def empty_target(con):
    existing = con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=current_schema() AND table_type='BASE TABLE'").fetchall()
    if existing: raise ValueError('Docelowy schemat PostgreSQL musi być pusty. Migracja nie nadpisuje istniejących tabel.')

def copy_snapshot(source_path, backup_path):
    # backup() takes a consistent snapshot, including committed WAL contents.
    with closing(sqlite3.connect(source_path.as_uri() + '?mode=ro', uri=True)) as source:
        with closing(sqlite3.connect(backup_path)) as backup:
            source.backup(backup)

def migrate(source_path, url, backup_dir=None):
    source_path = Path(source_path).resolve()
    if not source_path.is_file(): raise ValueError('Nie znaleziono źródłowej bazy SQLite.')
    with database.connect(url) as target:
        target.begin_write()
        empty_target(target)
    backup_dir = Path(backup_dir or ROOT / 'data' / 'backups')
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    backup_path = backup_dir / f'before-postgres-{stamp}.sqlite3'
    copy_snapshot(source_path, backup_path)
    # Update only a disposable snapshot to the application's latest SQLite schema.
    with tempfile.TemporaryDirectory(prefix='edoc-migration-') as temporary:
        working = Path(temporary) / 'source.sqlite3'
        copy_snapshot(backup_path, working)
        old_url, old_path = os.environ.get('DATABASE_URL'), os.environ.get('EDOCUMENTS_DB')
        os.environ['DATABASE_URL'], os.environ['EDOCUMENTS_DB'] = '', str(working)
        try:
            main = importlib.import_module('backend.main')
        finally:
            for key, value in [('DATABASE_URL', old_url), ('EDOCUMENTS_DB', old_path)]:
                if value is None: os.environ.pop(key, None)
                else: os.environ[key] = value
        previous = main.DATABASE_URL, main.DB_PATH, main.db
        try:
            main.DATABASE_URL, main.DB_PATH = '', working
            main.initialize()
            with closing(sqlite3.connect(working)) as source, database.connect(url) as target:
                source.row_factory = sqlite3.Row
                target.begin_write()
                target.ensure_schema()
                empty_target(target)
                @contextmanager
                def same_transaction():
                    yield target
                main.db = same_transaction
                main.initialize()
                target.execute('DELETE FROM templates')
                counts = {}
                for table in ordered_tables(source):
                    columns = [row['name'] for row in source.execute(f'PRAGMA table_info({identifier(table)})')]
                    if set(columns) != target.columns(table): raise ValueError(f'Niezgodny schemat tabeli: {table}')
                    query = f'INSERT INTO {identifier(table)}({",".join(map(identifier, columns))}) VALUES({",".join("?" for _ in columns)})'
                    rows = ordered_rows(source, table)
                    for row in rows: target.execute(query, tuple(row))
                    imported = target.execute(f'SELECT * FROM {identifier(table)}').fetchall()
                    if fingerprint(rows) != fingerprint(imported): raise ValueError(f'Weryfikacja danych nie powiodła się: {table}')
                    counts[table] = len(rows)
                target.execute("SELECT setval(pg_get_serial_sequence('resource_history','id'), COALESCE((SELECT max(id) FROM resource_history),1), EXISTS(SELECT 1 FROM resource_history))")
        finally:
            main.DATABASE_URL, main.DB_PATH, main.db = previous
    return backup_path, counts

def cli():
    config = dotenv_values(ROOT / '.env')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(os.getenv('EDOCUMENTS_DB') or config.get('EDOCUMENTS_DB') or ROOT / 'data' / 'documents.sqlite3'))
    parser.add_argument('--check', action='store_true', help='Check connectivity and an empty target without changing data')
    args = parser.parse_args()
    url = os.getenv('DATABASE_URL') or config.get('DATABASE_URL')
    if config.get('DATABASE_SCHEMA') and 'DATABASE_SCHEMA' not in os.environ:
        os.environ['DATABASE_SCHEMA'] = config['DATABASE_SCHEMA']
    if not url: parser.error('Uzupełnij DATABASE_URL w .env.')
    try:
        if args.check:
            with database.connect(url) as target:
                empty_target(target)
            print('Połączenie PostgreSQL działa; docelowy schemat jest pusty.')
            return
        backup, counts = migrate(args.source, url)
    except (ValueError, database.psycopg.Error, sqlite3.Error) as exc:
        # Never print connection URLs or credentials.
        print(str(exc) if isinstance(exc, ValueError) else 'Operacja nie powiodła się. Sprawdź połączenie i uprawnienia bazy; aplikacja nie została przełączona.')
        raise SystemExit(1) from None
    print(f'Kopia źródła: {backup}')
    for table, count in counts.items(): print(f'{table}: {count}')
    print('Migracja zakończona. Liczby i zawartość rekordów zweryfikowane. Uruchom ponownie backend.')

if __name__ == '__main__': cli()
