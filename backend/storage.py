"""Private object storage; credentials are configured only on the server."""
import logging
import os
import secrets
from functools import lru_cache

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException

logger = logging.getLogger(__name__)

def enabled():
    return os.getenv('EDOCUMENTS_STORAGE', 'sqlite') == 's3'

@lru_cache(maxsize=1)
def client():
    return boto3.client(
        's3', endpoint_url=os.getenv('S3_ENDPOINT_URL') or None,
        region_name=os.getenv('S3_REGION', 'us-east-1'),
        aws_access_key_id=os.getenv('S3_ACCESS_KEY_ID') or None,
        aws_secret_access_key=os.getenv('S3_SECRET_ACCESS_KEY') or None,
        aws_session_token=os.getenv('S3_SESSION_TOKEN') or None,
        config=Config(signature_version='s3v4',
                      s3={'addressing_style': os.getenv('S3_ADDRESSING_STYLE', 'path')},
                      request_checksum_calculation='when_required',
                      response_checksum_validation='when_required',
                      connect_timeout=5, read_timeout=30,
                      retries={'max_attempts': 2, 'mode': 'standard'}))

def put(data, user_id):
    if not enabled():
        return None, None
    bucket = os.getenv('S3_BUCKET')
    if not bucket:
        raise HTTPException(503, 'Magazyn plików S3 nie jest skonfigurowany.')
    prefix = os.getenv('S3_PREFIX', 'edokumenty').strip('/')
    key = '/'.join(part for part in [prefix, user_id, secrets.token_hex(24)] if part)
    try:
        client().put_object(Bucket=bucket, Key=key, Body=data, ContentType='application/octet-stream')
    except (BotoCoreError, ClientError):
        raise HTTPException(503, 'Nie udało się zapisać pliku w magazynie S3.') from None
    return bucket, key

def get(bucket, key):
    try:
        return client().get_object(Bucket=bucket, Key=key)['Body']
    except ClientError as exc:
        if exc.response.get('Error', {}).get('Code') in ('NoSuchKey', '404'):
            raise HTTPException(404, 'Plik nie istnieje w magazynie S3.') from None
        raise HTTPException(503, 'Nie udało się pobrać pliku z magazynu S3.') from None
    except BotoCoreError:
        raise HTTPException(503, 'Magazyn S3 jest niedostępny.') from None

def delete(bucket, key):
    if not key:
        return
    try:
        client().delete_object(Bucket=bucket, Key=key)
    except (BotoCoreError, ClientError):
        raise HTTPException(503, 'Nie udało się usunąć pliku z magazynu S3. Spróbuj ponownie.') from None

def cleanup(bucket, key):
    try:
        delete(bucket, key)
    except HTTPException:
        logger.warning('Nie udało się usunąć nieużywanego obiektu S3: %s/%s', bucket, key)
