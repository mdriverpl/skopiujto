# REST API

Dokumentacja backendu: `/api/docs` (Swagger), `/api/redoc` oraz
`/api/openapi.json` (OpenAPI). API obejmuje dokumenty, pliki, foldery,
uprawnienia, historię, szablony, zadania, wiadomości i ankiety.
`GET /api/health` sprawdza dostępność bazy bez ujawniania konfiguracji.

`DELETE /api/surveys/{id}` pozwala autorowi trwale usunąć ankietę wraz z
odpowiedziami, wynikami, zaproszeniami i zapisaną interpretacją. Linki do usuniętej
ankiety przestają działać. Odbiorca otrzymuje 403, a osoba bez dostępu 404.

Biblioteka ankiet specjalnych: `GET /api/surveys/presets/phq9` zwraca gotowy
formularz PHQ-9. `POST /api/surveys` z `scoring_profile: "phq9"` wymaga
niezmienionych dziewięciu pytań i opcji. Każda przesłana odpowiedź otrzymuje
wynik `result` z punktami każdego pytania (0–3), sumą (0–27), nasileniem
objawów i oznaczeniem potrzeby konsultacji przy dodatniej odpowiedzi na pytanie 9.
Wynik jest obliczany przez serwer i dostępny również po ponownym otwarciu
formularza. Autor widzi wyniki poszczególnych uczestników; uczestnik tylko swój.
Profile PHQ-9 używają stałego klucza punktacji, a nie oceny z promptu AI.
Źródła: [polski formularz PHQ](https://projectteachny.org/app/uploads/2022/07/PHQ_Polish-for-Poland.pdf),
[instrukcja PHQ](https://www.phqscreeners.com/images/sites/g/files/g10016261/f/201412/instructions.pdf).

`POST /api/ai/generate` z `kind: "survey"` i `prompt` przygotowuje niezapisaną
ankietę: tytuł, opis i pytania z typami oraz opcjami odpowiedzi. Wymaga
zalogowania i konfiguracji AI na serwerze. Po sprawdzeniu i edycji wynik
można zapisać przez `POST /api/surveys`; generowanie nie wysyła zaproszeń.

`POST /api/surveys/{id}/interpretation` tworzy i zapisuje interpretację AI przesłanych odpowiedzi
z opcjonalnymi wskazówkami autora w JSON `{"prompt": "Skup się na przyczynach niezadowolenia"}`
(maksymalnie 8000 znaków). Pusty prompt oznacza analizę ogólną. Prompt jest
zapisywany razem z interpretacją i zwracany w jej polu `prompt`.
Analiza obejmuje podsumowanie, wnioski, proponowane działania i ograniczenia.
Operacja wymaga autorstwa ankiety i co najmniej jednej odpowiedzi.
Obejmuje odbiorców wewnętrznych oraz linki e-mail/SMS. Do AI nie trafiają nazwy,
adresy ani tokeny odbiorców; treść odpowiedzi pozostaje materiałem analizy.
`GET /api/surveys/{id}` udostępnia autorowi wynik w `interpretation`, z datą,
liczbą analizowanych odpowiedzi i flagą `stale` wskazującą zmianę wyników.

`POST /api/surveys/interpretation` przyjmuje `survey_ids` (od 1 do 10 ankiet)
i opcjonalny `prompt`. Każda ankieta autora z przesłanymi odpowiedziami jest
analizowana osobno, a następnie powstaje wspólne podsumowanie. Odpowiedź zawiera
`surveys` z osobnymi interpretacjami oraz `summary` z wnioskami przekrojowymi.
Osobne interpretacje zapisują się przy ankietach; wspólne podsumowanie jest
wyświetlane w bieżącej sesji w zakładce „Analiza odpowiedzi”.

Oba endpointy interpretacji przyjmują `grading: true`, aby dodać ocenę ankiety.
W tym trybie wymagany jest niepusty `prompt` opisujący skalę i kryteria oceny.
Ocena zapisuje się w `grade` (`value`, `scale`, `criteria`, `justification`)
i jest prezentowana na końcu interpretacji. Bez oceniania `grade` jest `null`.
Oceny dotyczą osobnych ankiet; podsumowanie zbiorcze nie otrzymuje oceny.

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
