"""Standalone IMAP receiver and Web Push dispatcher: python -m backend.background_worker."""
import logging
import os
import signal
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from backend import client_mail, mail_settings, mail_sync, webpush

log = logging.getLogger(__name__)


@contextmanager
def lease(db, key):
    # Session lock lives on a separate connection; no transaction spans IMAP I/O.
    with db() as con:
        acquired = con.execute('SELECT pg_try_advisory_lock(?) AS acquired', (key,)).fetchone()['acquired']
        con.raw.commit()
        try:
            yield acquired
        finally:
            if acquired:
                con.execute('SELECT pg_advisory_unlock(?)', (key,))


def sync_mail(db, hours=168):
    imported = 0
    with lease(db, 1745026011) as acquired:
        if not acquired:
            return 0
        with db() as con:
            accounts = con.execute("""SELECT u.id FROM users u
                JOIN client_mail_settings s ON s.user_id=u.id
                WHERE u.active=1 AND u.deleted_at IS NULL AND u.must_change_password=0
                AND (s.config::jsonb -> 'imap' ->> 'enabled')='true'""").fetchall()
        for account in accounts:
            try:
                with db() as con:
                    config = mail_settings.imap_config(con, account)
                result = mail_sync.receive(db, account, config, client_mail.parse_message,
                    lambda: datetime.now(timezone.utc).isoformat(), hours)
                imported += result['imported']
                log.info('IMAP account=%s imported=%s remaining=%s skipped=%s',
                         account['id'], result['imported'], result['remaining'], result['skipped'])
            except Exception:
                # Do not log credentials or private provider responses.
                log.warning('IMAP account=%s failed; retrying next cycle', account['id'])
    return imported


def dispatch_push(db):
    with lease(db, 1745026012) as acquired:
        if acquired:
            webpush.dispatch(db)


def repeat(action, stop, interval, name):
    while not stop.is_set():
        started = time.monotonic()
        try:
            action()
            log.info('%s cycle complete', name)
        except Exception:
            log.warning('%s cycle failed; retrying next cycle', name)
        stop.wait(max(1, interval - (time.monotonic() - started)))


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    interval = int(os.getenv('EDOCUMENTS_BACKGROUND_INTERVAL', '30'))
    hours = int(os.getenv('EDOCUMENTS_BACKGROUND_MAIL_HOURS', '168'))
    if interval < 10 or hours not in mail_sync.ALLOWED_HOURS:
        raise SystemExit('Use interval >= 10 and mail hours: 24, 48, 168 or 720')
    # Initialize schema once, without starting the HTTP server or its dispatcher.
    os.environ['EDOCUMENTS_WEBPUSH_WORKER'] = '0'
    from backend.main import db
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    log.info('Background worker started: interval=%ss mail_hours=%s push_configured=%s',
             interval, hours, webpush.configured())
    receiver = threading.Thread(target=repeat,
        args=(lambda: sync_mail(db, hours), stop, interval, 'IMAP'), daemon=True)
    receiver.start()
    repeat(lambda: dispatch_push(db), stop, interval, 'Web Push')
    receiver.join(timeout=20)


if __name__ == '__main__':
    main()
