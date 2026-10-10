"""SMSAPI delivery: accept only a confirmed provider response, never auto-retry."""
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values
from fastapi import HTTPException

ENV_FILE = Path(__file__).resolve().parents[1] / '.env'

def phone_number(value):
    compact = re.sub(r'[\s()\-]', '', value)
    if compact.startswith('00'): compact = '+' + compact[2:]
    if re.fullmatch(r'\d{9}', compact): compact = '+48' + compact
    if not re.fullmatch(r'\+[1-9]\d{7,14}', compact):
        raise ValueError('Podaj numer telefonu z kodem kraju, np. +48 600 123 456.')
    return compact


def configuration():
    local = dotenv_values(ENV_FILE)
    def setting(name): return (os.getenv(name) or local.get(name) or '').strip()
    token, sender = setting('SMSAPI_TOKEN'), setting('SMSAPI_SENDER')
    public_url = setting('EDOCUMENTS_PUBLIC_URL').rstrip('/')
    if not token or not public_url:
        raise HTTPException(503, 'Uzupełnij SMSAPI_TOKEN i EDOCUMENTS_PUBLIC_URL w .env, aby wysyłać SMS.')
    try:
        parts = urlsplit(public_url)
        valid = (parts.scheme in ('http', 'https') and parts.hostname and not parts.username
                 and not parts.password and not parts.query and not parts.fragment and not parts.path
                 and not any(char.isspace() for char in public_url))
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(503, 'EDOCUMENTS_PUBLIC_URL musi być publicznym adresem aplikacji bez ścieżki.')
    if sender and not re.fullmatch(r'[A-Za-z0-9 _-]{1,11}', sender):
        raise HTTPException(503, 'SMSAPI_SENDER musi mieć najwyżej 11 znaków: litery, cyfry, spacja, _ lub -.')
    return {'token': token, 'sender': sender, 'public_url': public_url}


def settings_status():
    try:
        configuration()
        return {'configured': True, 'message': ''}
    except HTTPException as exc:
        return {'configured': False, 'message': exc.detail}


def send_link(config, phone, filename, version, link, days):
    message = f'Plik do akceptacji: {filename[:60]} (v{version}).\n{link}\nWazny {days} dni.'
    if len(message) > 400:
        raise HTTPException(503, 'Adres aplikacji jest za długi, aby wysłać link SMS-em.')
    return send_text(config, phone, message)

def send_text(config, phone, message):
    if not message.strip() or len(message) > 1200:
        raise HTTPException(422, 'Treść SMS musi mieć od 1 do 1200 znaków.')
    params = {'to': phone.lstrip('+'), 'message': message, 'format': 'json', 'encoding': 'utf-8'}
    if config['sender']: params['from'] = config['sender']
    try:
        with httpx.Client(timeout=httpx.Timeout(20, connect=10)) as client:
            response = client.post('https://api.smsapi.pl/sms.do', data=params,
                                   headers={'Authorization': f"Bearer {config['token']}"})
        result = response.json()
        items = result.get('list', [])
        if (response.status_code != 200 or result.get('error') or result.get('count') != 1
                or len(items) != 1 or not items[0].get('id') or items[0].get('error')
                or str(items[0].get('number', '')).lstrip('+') != phone.lstrip('+')):
            raise ValueError('Not accepted')
        return str(items[0]['id'])
    except (httpx.RequestError, ValueError, TypeError, KeyError, AttributeError):
        raise HTTPException(503, 'SMSAPI nie potwierdziło przyjęcia SMS. Sprawdź konfigurację, saldo i numer odbiorcy.') from None
