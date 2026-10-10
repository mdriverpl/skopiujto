# PostgreSQL

Backend wybiera PostgreSQL, gdy `DATABASE_URL` w `.env` jest uzupełnione.
Puste `DATABASE_URL` zachowuje SQLite do migracji i testów. Pliki nadal
korzystają z ustawionego magazynu S3; pliki zapisane w SQLite migrują
do kolumn `BYTEA` w PostgreSQL.

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
DATABASE_SCHEMA=edokumenty
```

Znaki specjalne w haśle zakoduj jako część URL (np. `@` → `%40`, `#` → `%23`).
Użytkownik musi mieć dostęp do bazy i prawo tworzenia schematu, tabel oraz
indeksów. Tabele aplikacji są w osobnym schemacie `edokumenty`.
Inne schematy nie są modyfikowane. Skonfigurowany PostgreSQL nie przełącza
się automatycznie na SQLite w przypadku błędu połączenia.

Zależności:

```powershell
& ./.runtime/python/python.exe -m pip install -r backend/requirements.txt
```

Przeniesienie istniejących danych:

1. Uzupełnij połączenie w `.env` i sprawdź dostęp do pustego schematu:

   ```powershell
   & ./.runtime/python/python.exe -m backend.migrate_postgres --check
   ```

2. Zatrzymaj wszystkie procesy backendu, żeby nikt nie zapisywał nowych danych
   w SQLite podczas migracji.
3. Wykonaj migrację:

   ```powershell
   & ./.runtime/python/python.exe -m backend.migrate_postgres --source data/documents.sqlite3
   ```

4. Po komunikacie o powodzeniu uruchom ponownie backend.

Migrator tworzy spójną kopię SQLite w `data/backups`. Oryginalny plik zostaje
niezmieniony. Import odbywa się w jednej transakcji i odmawia nadpisania
istniejących tabel w docelowym schemacie. Porównuje liczbę oraz zawartość
wszystkich rekordów, również plików. Zachowuje identyfikatory, hasła, sesje,
historię, klucze API i uprawnienia. Zachowuje również kolejność odbiorców wysyłek.

Po nieudanym imporcie możesz uruchomić SQLite, pozostawiając `DATABASE_URL`
puste. Po rozpoczęciu pracy na PostgreSQL powrót do starego pliku SQLite nie
przenosi nowych zmian. Nie używaj obu baz równolegle.

Bieżące kopie PostgreSQL wykonuj przez
[pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html)
lub mechanizm kopii u dostawcy. Kopia sprzed migracji obejmuje tylko źródłową bazę.

Testy PostgreSQL wymagają osobnej bazy. Tworzą losowe schematy i usuwają tylko
te schematy. Nigdy nie podawaj bazy produkcyjnej jako testowej:

```powershell
$env:EDOCUMENTS_TEST_DATABASE_URL='postgresql://USER:PASSWORD@127.0.0.1:5432/edokumenty_test'
& ./.runtime/python/python.exe -m pytest backend -q --tb=short
```

Bez tej zmiennej testy używają tymczasowych baz SQLite; test importu do
PostgreSQL jest pomijany.
