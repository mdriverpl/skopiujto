# PWA na Androidzie i Windowsie

Po zalogowaniu otwórz menu konta → **Aplikacja i powiadomienia**.
Instalacja działa w Chrome i Edge. Używa zwykłego logowania, bez parowania QR.

## Uruchomienie

1. Zainstaluj backend: `python -m pip install -r backend/requirements.txt`.
2. Zbuduj frontend: `npm run build`.
3. Udostępnij aplikację przez HTTPS z API na tym samym originie. Na komputerze
   testy mogą działać na localhost; HTTP przez adres LAN komputera nie wystarczy na telefonie.
4. Ustaw `EDOCUMENTS_PUBLIC_URL` i wygeneruj klucze:
   `python scripts/configure_webpush.py --subject https://twoja-domena.pl`.
   Skrypt zapisuje klucze do ignorowanego `.env`, bez wypisywania sekretu.
   Alternatywny subject: `mailto:administrator@twoja-domena.pl`.
5. Zrestartuj backend. Zachowaj klucze przy aktualizacjach i we wszystkich replikach.
6. Na każdym urządzeniu zaloguj się i wybierz **Włącz powiadomienia**,
   zaakceptuj zgodę, a następnie **Wyślij test**.

Nie publikuj prywatnego klucza ani `.env`. Do przeglądarki trafia tylko klucz publiczny.
Dispatcher działa w backendzie co 30 sekund, a kolejka i deduplikacja są w PostgreSQL.
`EDOCUMENTS_WEBPUSH_WORKER=0` wyłącza dispatcher (np. w testach).

## Zakres

- Nowe nieprzeczytane wiadomości wewnętrzne i e-maile w odebranych, poza spamem.
  Poczta musi już trafić do eDokumentów przez istniejącą synchronizację.
- Nowe aktywne zadania przypisane użytkownikowi.
- Przypomnienia o zadaniach oraz terminach własnych dokumentów po wejściu
  w okno najbliższych 24 godzin i najbliższej godziny.
- Wybór kategorii, nazwa urządzenia, test i zdalne odłączenie urządzenia.
- Kliknięcie otwiera sekcję wiadomości, zadań lub terminarza; obowiązuje normalne logowanie.
- Wiadomości/zadania sprzed włączenia subskrypcji nie są wysyłane.
  Przypomnienia dotyczą również istniejących, przyszłych terminów.
- Wylogowanie, wygaśnięcie sesji (obecnie 7 dni), reset hasła lub zablokowanie konta
  zatrzymuje wysyłkę. Po ponownym logowaniu włącz ją ponownie.

Web Push nie gwarantuje czasu dostarczenia. Potrzebne są internet i zgody przeglądarki
oraz systemu. Uśpienie, tryb skupienia i ograniczenia pracy w tle mogą opóźniać lub
blokować alerty. Zamknięta karta nie wymaga odpytywania serwera, ale wymuszone
zatrzymanie przeglądarki lub wyłączony komputer uniemożliwia bieżący odbiór.
To nie jest alarm offline ani kanał gwarantowanego doręczenia.

Nieudana wysyłka jest ponawiana maksymalnie 8 razy; odpowiedź 404/410 usuwa
wygasłą subskrypcję. Awaria po wysłaniu, a przed zapisem potwierdzenia może
spowodować ponowne doręczenie. Zmiana terminu, zakończenie zadania i cofnięcie
preferencji unieważnia oczekujące alerty. Treści wiadomości nie są wysyłane.

## Offline i aktualizacje

Service worker zapisuje wyłącznie publiczne ikony i stronę „Brak połączenia”.
Nie zapisuje API, dokumentów ani stron konta. Przy braku sieci pokazuje komunikat.
PWA nie oferuje edycji offline. Przy zmianie publicznych zasobów zwiększ
wersję cache w `public/sw.js`.

## Weryfikacja na urządzeniu

Na Windowsie i Androidzie sprawdź test push, nowe wiadomości i zadanie, kliknięcie
alertu, zamkniętą kartę, wygaszony ekran, odłączenie, wylogowanie i brak internetu.
Automatyczne testy używają atrap dostawcy i nie zastępują testu rzeczywistego transportu.

Dokumentacja: [Web Push](https://developer.mozilla.org/en-US/docs/Web/API/Push_API),
[manifest](https://web.dev/articles/add-manifest),
[pywebpush](https://github.com/web-push-libs/pywebpush).
