# REST API

Dokumentacja backendu: `/api/docs` (Swagger), `/api/redoc` oraz
`/api/openapi.json` (OpenAPI). API obejmuje dokumenty, pliki, foldery,
uprawnienia, historię, szablony, zadania, wiadomości i ankiety.
`GET /api/health` sprawdza dostępność bazy bez ujawniania konfiguracji.

Przeglądarka loguje się przez `POST /api/login` i cookie `session`.
Do integracji służą osobiste klucze API. Po zalogowaniu otwórz Swagger
i wykonaj `POST /api/access-tokens`:

```json
{"name": "Integracja CRM", "scope": "read", "expires_days": 90}
```

Odpowiedź zawiera `id` i jednorazowo jawną wartość `token`. Zapisz token
po stronie integracji; baza przechowuje tylko jego skrót. Kolejne żądania:

```http
GET /api/documents
Authorization: Bearer edoc_TWOJ_KLUCZ
```

`read` pozwala na odczyt, `write` również na zapis dostępny dla właściciela
klucza. Klucz nie rozszerza uprawnień konta ani grup. Ważność: 1–365 dni,
domyślnie 90; maksymalnie 20 aktywnych kluczy na konto.
`GET /api/access-tokens` zwraca klucze bez ich wartości;
`DELETE /api/access-tokens/{id}` unieważnia klucz. Zarządzanie kluczami wymaga
sesji przeglądarki. Klucz API nie może tworzyć następnych kluczy.
Zmiana/reset hasła lub blokada konta unieważnia jego klucze.

Błędy: 401 — brak/wygaśnięcie uwierzytelnienia, 403 — brak uprawnień,
404 — obiekt niedostępny lub nieistniejący, 409 — konflikt wersji lub stanu,
422 — niepoprawne dane. Aktualizacja dokumentów wymaga `version`.
Pliki wysyła się przez `multipart/form-data` do `/api/files`.
Schematy żądań i lista dostępnych operacji znajdują się w OpenAPI.

Integracje powinny łączyć się przez HTTPS. Ustaw
`EDOCUMENTS_SECURE_COOKIE=1`, gdy aplikacja jest udostępniana przez HTTPS.

Sterownik bazy: [Psycopg 3](https://www.psycopg.org/psycopg3/docs/).
