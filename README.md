# eDokumenty

Aplikacja Vue z backendem FastAPI i bazą PostgreSQL. Po zalogowaniu otwiera się „Start” z robotem,
ankietami do wypełnienia i zadaniami użytkownika. Kafelki katalogów i plików
pokazują zasoby wymagające działania na podstawie niezakończonych zadań.
Dysk z plikami i folderami jest dostępny w zakładce „Mój dysk”. Pliki mogą
być zapisywane w bazie lub magazynie S3. Ikona palety obok nazwy użytkownika
otwiera wybór motywu: normalny, słodki, ciemny i kolorowy. Wybór jest
zapamiętywany w tej przeglądarce.

GitHub Actions automatycznie testuje projekt, buduje frontend oraz obraz Docker
po zmianach na `main`. Testy backendu działają na izolowanej bazie PostgreSQL.
Po udanych testach oraz sprawdzeniu kontenera obraz trafia do
`ghcr.io/mdriverpl/skopiujto:latest`; dostępny jest też tag z pełnym SHA commita.
Build frontendu można pobrać jako artefakt `frontend-dist` w zakładce
[Actions](https://github.com/mdriverpl/skopiujto/actions).

Docker Compose: `docker compose pull`, a następnie `docker compose up -d`
pobiera obraz zbudowany na GitHubie i uruchamia aplikację na
http://localhost:8080. Kontener korzysta z PostgreSQL i pozostałych ustawień
z lokalnego `.env`; plik ten nie trafia do obrazu. `DATABASE_URL` musi być
uzupełnione. Opcjonalnie ustaw `APP_PORT`, aby zmienić port (domyślnie 8080).
Ustaw `EDOCUMENTS_PUBLIC_URL` na adres dostępny dla odbiorców wiadomości.
Frontend i API działają w jednym kontenerze. Stan sprawdzisz poleceniem
`docker compose ps`, a logi przez `docker compose logs -f app`.
Jeśli obraz jest prywatny, zaloguj się do `ghcr.io` przez `docker login ghcr.io`
kontem z dostępem do pakietu (token z uprawnieniem `read:packages`).
Opcjonalnie ustaw `APP_IMAGE_TAG` na SHA commita, aby użyć konkretnej wersji.
Lokalne budowanie jest nadal możliwe:
`docker compose -f compose.yaml -f compose.build.yaml up -d --build`.

Konfiguracja i migracja danych: [PostgreSQL](backend/POSTGRES.md).
Integracje i klucze: [REST API](backend/API.md); dokumentacja działa na `/api/docs`.

Uruchom frontend przez `npm run dev`. Backend:

```powershell
& ./.runtime/python/python.exe -m pip install -r backend/requirements.txt
& ./.runtime/python/python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Aplikacja: http://127.0.0.1:5173. Konfiguracja S3: [backend/S3.md](backend/S3.md).

## Użytkownicy, grupy i uprawnienia

Pierwsze konto utworzone podczas konfiguracji jest administratorem.
Nowy użytkownik dodawany przez administratora musi mieć adres e-mail.
Serwer generuje hasło tymczasowe i wysyła je razem z nazwą użytkownika i adresem
aplikacji przez skonfigurowane SMTP (SMTP_HOST, SMTP_FROM, EDOCUMENTS_PUBLIC_URL).
Błąd wysyłki przerywa tworzenie konta. Przy pierwszym logowaniu użytkownik musi
zmienić hasło, zanim otrzyma dostęp do dokumentów. Kliknięcie nazwy użytkownika
w górnym pasku otwiera opcję „Zmień hasło”; zmiana wymaga obecnego hasła oraz
dwukrotnego wpisania nowego (minimum 10 znaków) i kończy pozostałe sesje.
Reset hasła przez administratora również wymaga jego zmiany przy następnym
logowaniu. Dotychczasowe konta zachowują własne hasła.
Przy aktualizacji starszej bazy rolę administratora otrzymuje pierwsze
istniejące konto. Migracja zachowuje pliki i przypisuje ich autorów.

Zakładka „Użytkownicy i grupy” pozwala tworzyć i edytować konta, resetować
hasła, blokować konta, zmieniać role oraz zarządzać grupami i ich członkami.
Zamiast usuwać konto, administrator je blokuje, zachowując autorstwo plików.
Blokada i reset hasła kończą sesje użytkownika. Nie można zablokować własnego
konta ani odebrać sobie roli administratora.

Nowe konta mają domyślnie tylko odczyt. Uprawnienia konta dotyczą własnych
zasobów i folderów. Uprawnienia grup dają dostęp do zasobów innych osób
w wybranym folderze i jego podfolderach. Zakres „Cały dysk” obejmuje wszystkie
zasoby. Uprawnienia konta i grup sumują się; brak zaznaczenia nie jest zakazem,
który nadpisuje uprawnienie otrzymane z innej grupy.

Podczas tworzenia folderu trzeba wybrać „Tylko ja”, „Grupa” lub „Użytkownicy”.
Można zaznaczyć kilka grup lub osób oraz prawa dodawania, usuwania i edycji.
Wybrani odbiorcy zawsze otrzymują odczyt. Nowy folder ma własny zakres dostępu:
nie przejmuje uprawnień dysku ani folderu nadrzędnego. „Tylko ja” nie udostępnia
folderu członkom grup z dostępem do całego dysku. Twórca zachowuje prawa, które
miał w miejscu tworzenia folderu. Zwykły użytkownik może przekazać odbiorcom
tylko prawa, które sam posiada; administrator może nadać wszystkie.

Starsze foldery zachowują dotychczasowe dziedziczenie. Bezpośrednie uprawnienia
nadane nowemu folderowi obejmują jego podfoldery dziedziczące dostęp, aż do
kolejnego folderu z własnym wyborem odbiorców. Administrator może zmienić
uprawnienia grup do konkretnego folderu w panelu grup.

* Odczyt: przeglądanie i pobieranie.
* Edycja: treść, tytuł i opis dokumentów, nazwy folderów, komentarze, terminy
  oraz linki udostępnienia. Dokument może edytować wyłącznie jego twórca
  z uprawnieniem do edycji, także w grupach i na koncie administratora.
  Załącznik może zastąpić tylko jego autor.
* Dodawanie: nowe pliki, dokumenty i foldery w dozwolonym miejscu.
* Usuwanie: dokumenty i puste foldery. Plik może usunąć tylko osoba, która go
  dodała, z uprawnieniem do usuwania. Ta zasada dotyczy również administratora.

Edycja, dodawanie lub usuwanie włączają też odczyt. Administrator zarządza
dostępem, ale sama rola nie daje dostępu do cudzych plików. Sprawdzanie
uprawnień odbywa się w backendzie przy każdym żądaniu. Zmiany grup i ról
obowiązują również dla istniejących sesji. Publiczne linki udostępnienia
pozostają osobnym sposobem dostępu do odczytu do czasu wygaśnięcia lub
wyłączenia linku.

Testy: `& ./.runtime/python/python.exe -m pytest backend -q`.
Build frontendu: `npm run build`.

Przycisk „Obraz i metadane” przy pliku otwiera podgląd i tagi EXIF, jeśli plik
je zawiera. Autor z uprawnieniem do edycji może kadrować obraz myszą lub podać
współrzędne kadru, a następnie zmienić wymiary w pikselach z zachowaniem
proporcji lub bez. Edycja obsługuje PNG, JPEG, WebP i BMP; animacje i inne
formaty pozostają tylko do odczytu. Zapis zastępuje obraz, zachowuje obsługiwane
EXIF i zwiększa wersję. Limit: 10 MB, 10 000 px na bok i 40 milionów pikseli.
Nowsza wersja pliku nie jest nadpisywana.

## Aktywne dokumenty

Na głównej stronie „Mój dysk” kafelek „Aktywne dokumenty” pokazuje liczbę
pozycji wymagających działania ze wszystkich dostępnych folderów. Lista
obejmuje szkice, dokumenty w toku, do podpisania, do modyfikacji i do akceptacji,
a także pliki z oczekującymi akceptacjami oraz dokumenty z otwartymi terminami.
Można filtrować rodzaj działania, wyszukiwać dokumenty i otwierać ich foldery.
Dokument występuje raz, również gdy wymaga kilku działań.

Przycisk statusu przy pliku na dysku oraz „Zmień status” na liście pozwalają
autorowi z prawem edycji zmienić etap pracy. „Gotowy” kończy ręczny etap;
otwarte terminy lub akceptacje nadal oznaczają aktywność. „Archiwum” wyłącza
dokument z tej listy. Status „Do podpisania” oznacza potrzebę podpisu.

Oczekujące akceptacje autora obejmują wszystkie wysłane wersje, także po
modyfikacji oryginału lub zmianie jego statusu. Zaakceptowane, cofnięte,
wygasłe i niepotwierdzone wysyłki nie tworzą oczekującego działania.
Status i aktywność są sprawdzane w backendzie; cudze oraz prywatne dokumenty
zachowują dotychczasowe zasady dostępu.

## Historia zmian

Ikona „Historia zmian” przy dokumentach, plikach i katalogach oraz przycisk
„Historia” na szablonie pokazują datę, użytkownika i opis operacji. Szczegóły
zawierają poprzednie i nowe wartości zmienionych pól. Długie treści są skracane;
przy zmianie dokumentu pokazany jest fragment wokół pierwszej różnicy.

Rejestrowane są utworzenie, edycja i usunięcie obiektu, zastąpienie pliku,
kadrowanie i zmiana rozdzielczości obrazu, status dokumentu, komentarze, terminy,
linki udostępnienia oraz zmiany uprawnień grupy do katalogu. Wpis powstaje w tej
samej transakcji co zmiana; odrzucone zapisy nie tworzą historii. Nazwa użytkownika
jest zachowana z chwili operacji. Historia zaczyna się od uruchomienia tej funkcji.

Podgląd respektuje aktualny dostęp do obiektu; publiczne linki nie udostępniają
historii. Wpisy pozostają w bazie po usunięciu obiektu i są wtedy dostępne przez
API tylko jego właścicielowi. Lista ładuje po 100 wpisów z opcją „Starsze wpisy”.

## Ankiety

Ankietę zapisujesz bez odbiorców: podajesz tytuł, opis i maksymalnie 40 pól
(tekst, liczba, data, lista wyboru lub zaznaczenie). Odbiorców wybierasz później
przez przycisk „Wyślij do” na kafelku lub w szczegółach ankiety. Możesz wpisać
adresy e-mail/telefony ręcznie albo wybrać prywatny słownik, załadować dane,
zaznaczyć kontakty i dodać je do listy odbiorców. Wysyłka korzysta z istniejącej
konfiguracji SMTP/SMSAPI i EDOCUMENTS_PUBLIC_URL. Każda wysyłka obejmuje do 100
odbiorców; kolejna może dodać inne osoby.

Każda osoba otrzymuje indywidualny link /survey/<token>, ważny domyślnie 14 dni
(1–90 dni), i odpowiada bez konta w aplikacji. W bazie jest skrót tokenu, nie
jego jawna wartość. Odpowiedź jest zapisywana raz. Zamknięcie ankiety zatrzymuje
przyjmowanie odpowiedzi. Pytania po zapisaniu pozostają niezmienne.

Autor widzi odpowiedzi, statusy e-mail/SMS, daty wypełnienia, rozkłady pytań wyboru
oraz licznik wypełnionych, oczekiwanych i pozostałych odpowiedzi. Oczekiwane
obejmują wszystkich przypisanych odbiorców, także błędy wysyłki widoczne na liście.
Status „Wysłano” oznacza przyjęcie przez transport, nie przeczytanie wiadomości.
Powtórzenie tego samego żądania nie wysyła zaproszeń ponownie; ten sam adres
w danym kanale może mieć jedno zaproszenie w ankiecie. Istniejące przypisania
użytkowników w aplikacji i ich odpowiedzi pozostają dostępne w widoku „Dla mnie”.

## Polecenia AI i wiadomości

Zakładka „Wiadomości” pokazuje wiadomości odebrane i wysłane. Listę można
filtrować według odbiorcy/nadawcy, tematu lub treści oraz zakresu dat wysyłki.
„Nowa wiadomość” otwiera ręczny wybór odbiorców i formularz tematu/treści,
bez korzystania z OpenAI. „Nowa wiadomość AI” pozwala wpisać polecenie, np. „Wyślij do pracowników wiadomość:
Spotkanie na sali o godzinie 19:00”. Obsługiwaną operacją jest wysyłanie wiadomości.
Można szukać odbiorców w kontach użytkowników, prywatnych słownikach lub obu
listach (domyślnie). Można wskazać konkretny słownik i kanał: w aplikacji, e-mail
albo SMS. Bez wskazania kanału AI rozpoznaje go z polecenia, a aplikacja wybiera
wiadomość wewnętrzną, e-mail lub SMS według danych kontaktu.

„Przygotuj polecenie” tworzy podgląd, bez wysyłania. Można poprawić temat i treść
oraz odznaczyć odbiorców. Przycisk „Wyślij wiadomość” uruchamia wysyłkę.
Brakujące dane lub konfiguracja kanału są oznaczone przy osobie w podglądzie.
Niejasne polecenia wymagają doprecyzowania. AI wybiera tylko identyfikatory
istniejących osób z dostępnych użytkownikowi źródeł.

Wiadomości do kont trafiają do listy „Odebrane” w zakładce „Wiadomości”.
Odbiorca może oznaczyć je jako przeczytane. Lista „Wysłane” pokazuje wynik
dla każdej osoby i czas wysyłki. Kliknięcie tematu otwiera pełną treść.
Status e-mail/SMS oznacza przyjęcie przez transport, bez potwierdzenia dostarczenia
lub przeczytania. Niepotwierdzonych wysyłek system nie ponawia automatycznie;
polecenie można wykonać tylko raz. Podgląd wygasa po godzinie, a zmiana danych
odbiorcy wymaga ponownego przygotowania podglądu.

Funkcja korzysta z dotychczasowych OPENAI_API_KEY, OPENAI_MODEL, SMTP i SMSAPI.
Do OpenAI przesyła polecenie oraz nazwy, źródła i stanowiska/grupy potencjalnych
odbiorców, bez ich adresów e-mail i telefonów. Plan generuje przez
[Structured Outputs w Responses API](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
Testy zastępują OpenAI, SMTP i SMSAPI; nie wysyłają prawdziwych wiadomości.

## Słowniki

Zakładka „Słowniki” pokazuje kafelek „AI” i własne słowniki użytkownika.
AI korzysta z dotychczasowych automatycznie zapamiętywanych danych dokumentów;
po otwarciu prezentuje tabelę pól i wartości. Automatyczne zapisywanie
i dopasowywanie danych do dokumentów nadal korzysta z tych samych danych.

„Dodaj słownik” pozwala ustalić nazwę i kolumny, np. „Pracownicy” z polami
Imię, Nazwisko, Stanowisko, Telefon i E-mail. Ikona ołówka na kafelku lub
przycisk „Edytuj słownik” pozwala zmieniać nazwę słownika oraz dodawać,
usuwać i zmieniać nazwy jego pól. Zmiana nazwy pola zachowuje wartości,
nowe pola są puste, a usunięcie pola po potwierdzeniu usuwa jego wartości
ze wpisów. Słownik AI nie ma edycji struktury. W słowniku można wyszukiwać,
dodawać, edytować i usuwać wpisy. Własne słowniki są prywatne dla użytkownika,
nie dodają automatycznie swoich wpisów do pamięci AI. Usunięcie słownika usuwa
jego wpisy. Nazwa AI jest zarezerwowana dla istniejącej pamięci dokumentów.

W otwartym słowniku dostępne są „Eksport Excel” i „Import Excel”, również dla AI.
Eksport tworzy plik `.xlsx` z nazwami kolumn w pierwszym wierszu, zachowując
tekst i początkowe zera. Import czyta pierwszy arkusz; nagłówki muszą pasować
do pól słownika (kolejność i wielkość liter mogą być inne). Brakujące kolumny
pozostają puste. W AI kolumny to „Pole” i „Wartość”. Przed zapisaniem pokazuje
się podgląd pierwszych 10 wpisów i liczba wszystkich importowanych wpisów.
Import dopisuje dane, bez zastępowania istniejących. Obsługiwane są pliki
do 10 MB i maksymalnie 1000 wierszy; formuły należy zamienić na wartości.
Odczyt i zapis arkuszy korzysta z [openpyxl](https://openpyxl.readthedocs.io/en/stable/).

## Zadania

Zakładka „Zadania” zbiera przypisane zadania, akceptacje plików, własne dokumenty
oznaczone do podpisania lub modyfikacji oraz terminy zapisane przy dokumentach.
Filtr „Zadania dla mnie” pokazuje działania odbiorcy, a „Zadania wysłane” zadania
przekazane innym i prośby o akceptację wysłane przez aplikację, e-mail lub SMS.
Można wyszukiwać zadania i filtrować je według statusu.

„Nowe zadanie” pozwala wskazać tytuł, aktywnego użytkownika, rodzaj zadania,
opis i termin. Powiązanie można wybrać jako „Ogólne”, „Katalog” lub „Plik lub
dokument”. Przy katalogu widoczna jest jego ścieżka; zadanie ma przycisk otwarcia
powiązanego katalogu lub dokumentu. Odbiorca musi już mieć dostęp do wskazanego
zasobu, a przy zadaniu modyfikacji dokumentu także prawo jego edycji. Zadanie można
przypisać również sobie. Odbiorca rozpoczyna i kończy zadanie, a nadawca może je
anulować. Obie osoby widzą aktualny status. Zakończenie zadania potwierdza jego
wykonanie; podpis i status samego dokumentu obsługuje się w dokumencie.
Zakończenie terminu aktualizuje istniejący termin przy dokumencie.

## Wysyłanie plików i akceptacje

W oknie „Udostępnij do akceptacji” każdy odbiorca ma własny kanał: użytkownik
aplikacji, e-mail lub SMS. Można połączyć kanały w jednej wysyłce, do 20 odbiorców.
Historia nadawcy pokazuje kanał, odbiorcę, status i czas akceptacji.

Użytkownika wybiera się z listy aktywnych kont. Plik trafia do jego zakładki
„Zadania”, do filtra „Zadania dla mnie”. Licznik pokazuje oczekujące działania.
Odbiorca pobiera przesłaną
wersję i potwierdza jej akceptację. Nie musi mieć dostępu do folderu nadawcy;
otrzymuje dostęp do niezmiennej kopii tego konkretnego pliku. Inne konta nie
mogą pobrać ani zaakceptować tej prośby. Wysyłka wewnętrzna nie wymaga SMTP
ani publicznego adresu aplikacji.

SMS jest wysyłany przez [SMSAPI](https://www.smsapi.pl/docs/) i zawiera osobisty
link do pobrania oraz akceptacji tej wersji. W `.env` uzupełnij lokalnie:

```dotenv
SMSAPI_TOKEN=
SMSAPI_SENDER=
EDOCUMENTS_PUBLIC_URL=https://dokumenty.twoja-firma.pl
```

`SMSAPI_TOKEN` to token OAuth z uprawnieniem wysyłania SMS. `SMSAPI_SENDER`
jest opcjonalną, zatwierdzoną nazwą nadawcy (do 11 znaków); bez niej SMSAPI
korzysta z domyślnego pola nadawcy. Wpisuj telefony z kodem kraju, np.
`+48 600 123 456`; dziewięciocyfrowe numery są traktowane jako polskie.
SMS zawiera link, e-mail również załącznik. Dodatkowa wiadomość jest dostępna
na stronie akceptacji oraz w skrzynce użytkownika. Brak konfiguracji blokuje
wyłącznie wybrany kanał: użytkownik aplikacji działa również bez SMTP i SMSAPI.
Status wysłania SMS oznacza przyjęcie przez SMSAPI, a nie potwierdzenie dotarcia
na telefon. Niepotwierdzona wysyłka jest oznaczana jako błąd i nie daje dostępu
do pliku; aplikacja nie ponawia płatnej wysyłki automatycznie. Testy zastępują
transport SMS i SMTP, więc nie wysyłają prawdziwych wiadomości.

Ikona koperty przy pliku otwiera wysyłkę i historię akceptacji. Autor pliku
z uprawnieniem do edycji może wskazać do 20 odbiorców, imiona i nazwiska,
wiadomość oraz ważność dostępu (1–30 dni). Przy kanale e-mail każdy odbiorca
dostaje osobny e-mail z załącznikiem i osobistym linkiem. Odbiorcy nie widzą innych adresów.

Na stronie linku odbiorca pobiera przesłany plik, zaznacza potwierdzenie
i klika „Akceptuję plik”. Otwarcie e-maila, linku lub pobranie nie oznacza
akceptacji. Przy e-mailu i SMS nie trzeba zakładać konta: potwierdzenie jest przypisane
do adresu lub numeru, na który wysłano link, na podstawie posiadania tego linku.
Historia autora pokazuje odbiorcę, status i datę akceptacji; odświeża się co 15 sekund.
Przy pliku widoczna jest liczba akceptacji jego obecnej wersji.

Wysyłka zachowuje osobną kopię przesłanej wersji w skonfigurowanym magazynie
(S3 lub PostgreSQL). Zmiana oryginału nie zmienia załącznika ani pliku z linku.
Akceptacja wcześniejszej wersji pozostaje w historii i nie oznacza akceptacji
nowszej wersji. Autor może cofnąć oczekujący link. Usunięcie pliku usuwa
historię i kopie wysyłek oraz wyłącza linki; cofnięcie linku nie usuwa
załącznika, który już trafił na skrzynkę odbiorcy.

Konfiguracja w `.env` (wzór jest również w `.env.example`):

```dotenv
EDOCUMENTS_PUBLIC_URL=https://dokumenty.twoja-firma.pl
SMTP_HOST=smtp.twoja-firma.pl
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_FROM=dokumenty@twoja-firma.pl
SMTP_USERNAME=dokumenty@twoja-firma.pl
SMTP_PASSWORD=
```

Wpisz hasło lokalnie i uruchom ponownie backend. `SMTP_SECURITY` przyjmuje
`starttls`, `ssl` (zwykle port 465) lub `none` dla skonfigurowanego lokalnego
przekaźnika. `SMTP_USERNAME` i `SMTP_PASSWORD` mogą pozostać puste dla serwera
bez logowania. `EDOCUMENTS_PUBLIC_URL` musi prowadzić do aplikacji dostępnej
odbiorcom, bez dodatkowej ścieżki. Adres `localhost` działa tylko na komputerze,
na którym uruchomiono aplikację. Nie są potrzebne zmiany kluczy S3.

Bez konfiguracji SMTP wysyłka e-mail jest wyłączona, a formularz pokazuje brakujące
pola. Status wysłania oznacza przyjęcie wiadomości przez serwer SMTP;
historia nie potwierdza doręczenia do skrzynki. Błędy są zapisywane osobno
dla odbiorców i nie są oznaczane jako skuteczna wysyłka ani akceptacja.

## Szablony i edytor tekstu

Szablony mają widok kart z podglądem, wyszukiwanie oraz filtry kategorii i własnych
wzorów. „Nowy szablon” tworzy własny wzór, a „Utwórz kopię” zapisuje kopię gotowego
szablonu. Edytor obsługuje pogrubienie, kursywę, podkreślenie, przekreślenie,
czcionkę, rozmiar i kolor tekstu, nagłówki, wyrównanie, listy oraz cofanie zmian.

Formatowanie jest zapisywane jako walidowana struktura dokumentu i zachowywane
przy tworzeniu dokumentu z szablonu, jego dalszej edycji i udostępnianiu.
Własne szablony może edytować autor z uprawnieniem edycji. Gotowe wzory może
edytować administrator; pozostali użytkownicy mogą je przeglądać i kopiować.
Edycja aktualizuje istniejący szablon bez dodawania nowej pozycji.
Tworzenie wymaga uprawnienia dodawania.
Ikona kosza pozwala usunąć szablon po potwierdzeniu. Autor może usuwać własne
szablony z uprawnieniem usuwania, a administrator gotowe wzory. Usunięte gotowe
wzory nie wracają po restarcie serwera. Dokumenty utworzone z szablonu pozostają
na dysku.
Zapis sprawdza wersję szablonu, aby nie nadpisać zmian z innej karty przeglądarki.
Dotychczasowe szablony i dokumenty tekstowe pozostają dostępne po migracji.

## Uzupełnianie pól w dokumentach

Dokument zawierający miejsca oznaczone nawiasami, np. `[imię sprzedającego]`,
otwiera się z podglądem po lewej i formularzem po prawej. Wpisane dane od razu
pojawiają się we wszystkich wystąpieniach danego pola. Dla różnych danych używaj
odrębnych nazw, np. `[adres sprzedającego]` i `[adres kupującego]`.

Przycisk „Edytuj treść wzoru” pozwala zmieniać tekst i dodawać kolejne pola.
„Podgląd i dane” wraca do uzupełniania. Wzór i wpisane wartości są zapisywane
razem z dokumentem, więc pola pozostają dostępne po ponownym otwarciu.
Puste pola zachowują oznaczenia w nawiasach. Udostępniony dokument pokazuje
aktualną wypełnioną treść. Szablony zachowują pola do użycia w kolejnych dokumentach.
Limit wynosi 200 pól i 2000 znaków na wartość. Na małych ekranach formularz
pojawia się pod podglądem.

## Generowanie dokumentów i szablonów z AI

W oknie „Dodaj plik” wybierz „Z AI”, a w szablonach kliknij „Utwórz z AI”.
Wpisz prompt opisujący treść, strukturę i wymagania. Wygenerowana wersja robocza
otworzy się w edytorze. Zapis następuje dopiero po kliknięciu przycisku zapisu;
generowanie nie dodaje samo dokumentu ani szablonu.

W „Utwórz z AI” w szablonach można także załadować plik źródłowy: PDF,
DOC/DOCX, ODT, RTF, TXT/MD albo skan PNG/JPG/WEBP, maksymalnie 10 MB.
Po wybraniu pliku prompt jest opcjonalny i służy do dopisania wskazówek.
AI otrzymuje plik, zachowuje strukturę dokumentu i zamienia konkretne dane
na opisowe pola do uzupełnienia. Wynik jest wersją roboczą do sprawdzenia;
formatowanie i układ strony mogą różnić się od oryginału.

Konfiguracja w lokalnym pliku `.env`:

```dotenv
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
```

Wpisz własny klucz API OpenAI. Klucz jest odczytywany przez backend i nie trafia
do przeglądarki. Po uzupełnieniu konfiguracji otwórz ponownie okno AI. Model
można zmienić na zgodny z Responses API i Structured Outputs, dostępny na koncie.
Wywołania korzystają z limitu 4000 tokenów wyjściowych i czasu oczekiwania 60 s.
Prompt może mieć do 8000 znaków. Zapytania API są rozliczane na koncie OpenAI.

Do OpenAI jest przesyłany wpisany prompt oraz instrukcje tworzenia treści.
Aplikacja dołącza wyłącznie plik wybrany w formularzu, jeśli został załączony;
nie dołącza pozostałych plików z dysku ani innych szablonów. Żądanie używa
`store: false`. Wynik jest walidowany i przekształcany do struktury edytora.
Generowanie wymaga uprawnienia dodawania w bieżącym folderze (dokument)
lub na dysku głównym (szablon). Błędy połączenia, limitów, konfiguracji i odmowy
są pokazywane w formularzu bez automatycznego zapisu treści.

Implementacja korzysta z [Responses API i Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
Testy integracji używają zastępczego transportu HTTP i nie wykonują płatnych zapytań.
Pliki źródłowe są przekazywane jako [wejścia plikowe lub obrazowe OpenAI](https://developers.openai.com/api/docs/guides/file-inputs)
bez tworzenia trwałego pliku w Files API OpenAI ani zapisywania źródła na dysku aplikacji.

## Automatyczna pamięć danych i uzupełnianie AI

Dane wpisane w panelu uzupełniania dokumentu zapisują się automatycznie po
krótkiej przerwie w pisaniu. Nie trzeba wybierać zestawu ani klikać zapisu danych.
Kolejne wpisy w tym samym dokumencie aktualizują jego prywatną pamięć.
Przy zamykaniu formularza oraz zapisie dokumentu aplikacja wysyła oczekujące zmiany.
Pamięć jest niezależna od zapisu treści dokumentu: nawet dane wpisane w wersji
roboczej pozostają dostępne w „Słowniki → AI”.

AI sprawdza puste pola przy otwarciu formularza i po zmianach użytkownika.
Uwzględnia znaczenie pola, treść wzoru, wpisane dane stron oraz kontekst zapisanych
danych. Różne nazwy oznaczające tę samą daną mogą zostać dopasowane.
Przy kilku możliwych osobach, firmach lub wartościach pole powinno pozostać puste.
AI wybiera wyłącznie referencje do zapisanych wartości; serwer nie przyjmuje
wymyślonej wartości, nieznanej referencji ani dopasowania o niskiej pewności.
Uzupełnione pole pokazuje źródło i można je poprawić ręcznie.

Wpisane i świadomie wyczyszczone pola nie są nadpisywane. Zmiana danych przez
użytkownika unieważnia wcześniejsze wartości wstawione przez AI i uruchamia nowe
dopasowanie. Spóźniona odpowiedź dla poprzedniej treści lub tożsamości jest ignorowana.
Automatyczne uzupełnienie samo w sobie nie zapisuje nowej pamięci; zapamiętywane
są dane wpisywane ręcznie. Pozwala to ograniczyć powielanie błędnego dopasowania.

Słownik „AI” pokazuje wszystkie Twoje zapisane dane. Możesz je wyszukiwać,
poprawiać, usuwać i dodawać ręcznie przyciskiem „Dodaj dane”. Zestawy utworzone
wcześniej pozostają dostępne dla automatycznego dopasowania. Zmiana lub usunięcie
pamięci nie zmienia zapisanych dokumentów.

Dopasowanie używa skonfigurowanych `OPENAI_API_KEY` oraz `OPENAI_MODEL`.
Do OpenAI trafia treść wzoru (do 40 tys. znaków), wpisane wartości oraz prywatne
dane i ich kontekst z bieżącego konta, bez danych innych użytkowników.
Żądanie stosuje `store: false` i [Structured Outputs w Responses API](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
Nie wykonuje zapytań, gdy nie ma pamięci albo pustych pól. Zapytania są opóźniane
po zmianach, a równoległe dopasowanie dla jednego konta jest blokowane.
Błąd lub brak konfiguracji AI nie blokuje ręcznego wpisywania ani zapamiętywania danych.
Pewność modelu nie jest gwarancją poprawności: sprawdź dane przed zapisem lub podpisaniem.
Testy integracji zastępują odpowiedzi OpenAI; nie wykonują płatnych zapytań.

## Starter hostingu

Use this starter for a static microsite, click counter, or simple internal UI whose state is browser-scoped. It has no dependencies and needs no install.

Edit `worker/index.js`, then publish through the Sites hosting workflow with this starter's build and validation in `commands`.

The build copies only `worker/index.js` and `.openai/hosting.json`. Do not add standalone asset files. Embed any essential raster bytes in `worker/index.js` and serve or reference them as a data URL.

Pass these argument arrays as `commands`:

```json
[
  ["bash", "scripts/build.sh"],
  ["node", "scripts/validate-artifact.mjs"]
]
```

The deterministic build produces:

```text
dist/
├── .openai/
│   └── hosting.json
└── server/
    └── index.js
```

`dist/server/index.js` is an ES module with a default export containing `fetch(request, env, ctx)`. Edit `worker/index.js`, not the generated file under `dist/`.

## Edzio — polecenia ze strony Start

Ikona Edzia otwiera rozmowę, a mikrofon uruchamia dyktowanie po polsku. Po rozpoznaniu
mowy można poprawić tekst i kliknąć „Przygotuj”. AI wybiera rodzaj polecenia:

- „Zaplanuj spotkanie jutro o 9:00 w sali 4” — edytowalny podgląd osobistego wpisu
  z datą i godziną; zapis następuje po potwierdzeniu i otwiera terminarz.
- „Wyślij wiadomość do zespołu o spotkaniu” — podgląd treści i odbiorców w Wiadomościach;
  wysyłka następuje po kliknięciu „Wyślij wiadomość”.
- „Zrób dokument: oferta dla naszych pracowników” — generowanie wersji roboczej
  w edytorze; dokument pojawia się na dysku po zapisaniu.
- „Dodaj zadanie: przygotować ofertę do piątku” — podgląd zadania przypisanego do siebie.
  Przy niepełnej dacie można uzupełnić termin ręcznie.

Spotkanie jest osobistym zadaniem w kalendarzu. Zaproszenia do innych osób wymagają
osobnego polecenia wysyłki wiadomości. Niejasne lub wieloetapowe polecenie wywołuje
pytanie o doprecyzowanie. Dokumenty nadal wymagają uprawnienia dodawania na dysku.
Rozpoznawanie przez /api/ai/assistant/plan nie zapisuje ani nie wysyła danych.
Daty względne odnoszą się do strefy Europe/Warsaw; formularz edycji daty używa czasu
urządzenia, a kalendarz pokazuje godziny Europe/Warsaw.

Integracja korzysta z konfiguracji OPENAI_API_KEY i OPENAI_MODEL oraz
[Structured Outputs w Responses API](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
Testy backend/test_assistant.py zastępują transport AI i nie wykonują płatnych zapytań.
### Poczta Klienta

Menu **Poczta Klienta** otwiera listę wiadomości, podgląd treści i panel analizy AI. Wiadomości, szkice, etykiety, gwiazdki i foldery są przechowywane w PostgreSQL osobno dla każdego użytkownika. Dostęp do załączników wymaga sesji właściciela wiadomości.

- **Importuj .eml**: wczytanie wiadomości z załącznikami (maks. 10 MB). HTML jest zamieniany na tekst; zewnętrzne obrazy nie są ładowane. Synchronizacja IMAP nie jest jeszcze obsługiwana.
- **Napisz / Odpowiedz / Przekaż**: edytowalna treść i zapis w folderze Robocze. Przekazanie kopiuje treść bez załączników. Wysyłanie załączników nie jest jeszcze obsługiwane.
- **Ustawienia poczty** (ikona koła zębatego): adres e-mail, nazwa nadawcy i osobne dane SMTP oraz IMAP (serwer, port, SSL/TLS lub STARTTLS, login, hasło). Zapis dotyczy tylko bieżącego użytkownika. Puste hasło zachowuje zapisane hasło; zaznaczenie Usuń zapisane hasło usuwa je. Przycisk Zapisz i sprawdź testuje połączenie bez wysyłania lub pobierania wiadomości. Po zapisaniu konfiguracji IMAP przycisk Odśwież pocztę pobiera wiadomości z INBOX (do 100 na raz), bez duplikatów i bez oznaczania ich jako przeczytane na serwerze.
- **Wyślij**: korzysta z zapisanej osobistej konfiguracji SMTP. Przed jej pierwszym zapisem dostępna jest konfiguracja SMTP serwera; wyłączenie osobistego SMTP blokuje wysyłkę z Poczty Klienta. Niepowodzenie zachowuje szkic. Folder Wysłane oznacza przyjęcie przez SMTP, nie potwierdzone doręczenie.
- **Przeanalizuj wiadomość**: na żądanie przekazuje treść wiadomości do skonfigurowanego AI i zwraca podsumowanie, priorytet, zadania oraz propozycję odpowiedzi. Załączniki nie są analizowane. Użyj odpowiedzi otwiera edytor; wysyłka wymaga kliknięcia Wyślij.

Po aktualizacji uruchom ponownie backend, aby utworzyć tabele client_mail i client_mail_attachments oraz udostępnić endpointy /api/client-mail. Frontend buduje się poleceniem npm run build.

Hasła kont pocztowych są szyfrowane biblioteką cryptography (Fernet), nie są zwracane przez API i nie trafiają do konfiguracji jawnej w bazie. Klucz określa opcjonalne EDOCUMENTS_MAIL_SETTINGS_KEY; bez tej zmiennej aplikacja tworzy data/mail-settings.key. Zachowaj klucz wraz z kopiami bazy, aby po odtworzeniu można było odszyfrować hasła. Compose przechowuje katalog data w trwałym wolumenie mail-settings-data. Przy wielu instancjach ustaw ten sam klucz na wszystkich serwerach. Nowa tabela client_mail_settings powstaje podczas uruchomienia backendu.
