# PostgreSQL

Aplikacja i testy korzystaj? wy??cznie z PostgreSQL. `DATABASE_URL` jest
wymagane; brak konfiguracji lub b??d po??czenia przerywa uruchomienie.

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
DATABASE_SCHEMA=edokumenty
```

Znaki specjalne w ha?le zakoduj jako cz??? URL (np. `@` ? `%40`, `#` ? `%23`).
U?ytkownik musi mie? dost?p do bazy i prawo tworzenia schematu, tabel oraz
indeks?w. Tabele aplikacji s? w osobnym schemacie `edokumenty`.
Inne schematy nie s? modyfikowane.

Pliki korzystaj? z ustawionego magazynu S3. Przy `EDOCUMENTS_STORAGE=database`
s? przechowywane jako `BYTEA` w PostgreSQL. Wcze?niejsze za??czniki zapisane
w bazie pozostaj? dost?pne r?wnie? po w??czeniu S3.

Bie??ce kopie PostgreSQL wykonuj przez `pg_dump` lub mechanizm kopii u dostawcy.

Testy wymagaj? osobnej bazy. Tworz? losowe schematy i usuwaj? tylko te schematy.
Nigdy nie podawaj bazy produkcyjnej jako testowej:

```powershell
$env:EDOCUMENTS_TEST_DATABASE_URL='postgresql://USER:PASSWORD@127.0.0.1:5432/edokumenty_test'
& ./.runtime/python/python.exe -m pytest backend -q --tb=short
```

Bez tej zmiennej testy wymagaj?ce bazy ko?cz? si? czytelnym b??dem konfiguracji.
GitHub Actions uruchamia w?asny PostgreSQL do test?w i sprawdzenia kontenera.
