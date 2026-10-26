"""SMTP transport; credentials and the public application URL stay on the server."""
import mimetypes
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from urllib.parse import urlsplit

from email_validator import validate_email, EmailNotValidError
from fastapi import HTTPException

def configuration():
    host = os.getenv('SMTP_HOST', '').strip()
    sender = os.getenv('SMTP_FROM', '').strip()
    public_url = os.getenv('EDOCUMENTS_PUBLIC_URL', '').strip().rstrip('/')
    if not host or not sender or not public_url:
        raise HTTPException(503, 'Uzupełnij SMTP_HOST, SMTP_FROM i EDOCUMENTS_PUBLIC_URL w pliku .env na serwerze.')
    try:
        parts = urlsplit(public_url)
    except ValueError:
        raise HTTPException(503, 'Sprawdź poprawność EDOCUMENTS_PUBLIC_URL w .env.') from None
    if (parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or parts.path or any(char.isspace() for char in public_url)):
        raise HTTPException(503, 'EDOCUMENTS_PUBLIC_URL musi być adresem aplikacji, np. https://dokumenty.twoja-firma.pl, bez ścieżki.')
    try:
        sender = validate_email(sender, check_deliverability=False, allow_smtputf8=False).ascii_email
        security = os.getenv('SMTP_SECURITY', 'starttls').strip().lower()
        port = int(os.getenv('SMTP_PORT') or ('465' if security == 'ssl' else '587'))
        if security not in ('starttls', 'ssl', 'none') or not 1 <= port <= 65535:
            raise ValueError()
    except (ValueError, EmailNotValidError):
        raise HTTPException(503, 'Sprawdź SMTP_FROM, SMTP_PORT i SMTP_SECURITY (starttls, ssl lub none) w .env.') from None
    username = os.getenv('SMTP_USERNAME', '')
    password = os.getenv('SMTP_PASSWORD', '')
    if bool(username) != bool(password):
        raise HTTPException(503, 'Uzupełnij SMTP_USERNAME i SMTP_PASSWORD lub pozostaw oba puste dla serwera bez logowania.')
    return dict(host=host, port=port, sender=sender, security=security,
                username=username, password=password, public_url=public_url)

def settings_status():
    try:
        configuration()
        return {'configured': True, 'message': ''}
    except HTTPException as exc:
        return {'configured': False, 'message': exc.detail}

def clean_header(value):
    return ''.join(char for char in value if ord(char) >= 32 and ord(char) != 127)

def send_message(config, email, sender_name, subject, message, attachments=()):
    mail = EmailMessage()
    mail['From'] = config['sender']
    mail['To'] = email
    mail['Subject'] = clean_header(subject)[:200]
    mail['Date'] = formatdate(localtime=False)
    mail['Message-ID'] = make_msgid()
    mail.set_content(f'{message}\n\nWiadomość od: {sender_name}')
    for filename, data in attachments:
        mime, _ = mimetypes.guess_type(filename)
        main_type, sub_type = (mime or 'application/octet-stream').split('/', 1)
        mail.add_attachment(data, maintype=main_type, subtype=sub_type, filename=clean_header(filename))
    smtp = None
    try:
        if config['security'] == 'ssl':
            smtp = smtplib.SMTP_SSL(config['host'], config['port'], timeout=15, context=ssl.create_default_context())
        else:
            smtp = smtplib.SMTP(config['host'], config['port'], timeout=15)
            if config['security'] == 'starttls': smtp.starttls(context=ssl.create_default_context())
        if config['username']: smtp.login(config['username'], config['password'])
        refused = smtp.send_message(mail, from_addr=config['sender'], to_addrs=[email])
        if refused: raise smtplib.SMTPRecipientsRefused(refused)
    except (OSError, smtplib.SMTPException):
        raise HTTPException(503, 'SMTP nie potwierdziło przyjęcia wiadomości.') from None
    finally:
        if smtp:
            try: smtp.quit()
            except (OSError, smtplib.SMTPException): smtp.close()

def send_file(config, recipient, sender_name, filename, data, version, link, message, expires_at):
    mail = EmailMessage()
    mail['From'] = config['sender']
    mail['To'] = recipient['email']
    mail['Subject'] = clean_header(f'Plik do akceptacji: {filename}')[:250]
    mail['Date'] = formatdate(localtime=False)
    mail['Message-ID'] = make_msgid()
    text = (f"{sender_name} przesyła plik do akceptacji.\n\n"
            f"Plik: {filename}\nWersja: {version}\n"
            f"{('Wiadomość: ' + message + chr(10) + chr(10)) if message else ''}"
            f"Pobierz plik i potwierdź akceptację na stronie:\n{link}\n\n"
            f"Link jest ważny do: {expires_at} (UTC).\n"
            "Otwarcie wiadomości lub linku nie oznacza akceptacji. Potwierdź ją przyciskiem na stronie.\n"
            "Link jest przeznaczony dla Ciebie; nie przekazuj go innym osobom.")
    mail.set_content(text)
    mime, _ = mimetypes.guess_type(filename)
    main_type, sub_type = (mime or 'application/octet-stream').split('/', 1)
    mail.add_attachment(data, maintype=main_type, subtype=sub_type, filename=clean_header(filename))
    smtp = None
    try:
        if config['security'] == 'ssl':
            smtp = smtplib.SMTP_SSL(config['host'], config['port'], timeout=15, context=ssl.create_default_context())
        else:
            smtp = smtplib.SMTP(config['host'], config['port'], timeout=15)
            if config['security'] == 'starttls':
                smtp.starttls(context=ssl.create_default_context())
        if config['username']:
            smtp.login(config['username'], config['password'])
        refused = smtp.send_message(mail, from_addr=config['sender'], to_addrs=[recipient['email']])
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)
    except (OSError, smtplib.SMTPException):
        raise HTTPException(503, 'Serwer pocztowy nie potwierdził przyjęcia wiadomości. Sprawdź konfigurację SMTP i adres odbiorcy.') from None
    finally:
        if smtp:
            # A failed QUIT after a successful DATA response must not mark mail as unsent.
            try:
                smtp.quit()
            except (OSError, smtplib.SMTPException):
                smtp.close()
