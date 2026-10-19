"""Generate VAPID keys once, saving them only to the ignored local .env."""
import argparse
import base64
from pathlib import Path
from urllib.parse import urlsplit
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from dotenv import dotenv_values, set_key

parser = argparse.ArgumentParser()
parser.add_argument('--subject', help='Public HTTPS origin or mailto: administrator contact')
args = parser.parse_args()
path = Path(__file__).resolve().parents[1] / '.env'
settings = dotenv_values(path)
subject = args.subject or settings.get('EDOCUMENTS_WEBPUSH_SUBJECT') or settings.get('EDOCUMENTS_PUBLIC_URL', '')
parsed = urlsplit(subject)
if not ((parsed.scheme == 'https' and parsed.hostname) or (parsed.scheme == 'mailto' and '@' in parsed.path)):
    parser.error('Provide --subject https://your-domain.example or mailto:admin@your-domain.example')
if settings.get('EDOCUMENTS_WEBPUSH_PRIVATE_KEY') or settings.get('EDOCUMENTS_WEBPUSH_PUBLIC_KEY'):
    parser.error('Existing VAPID keys found. Keep them; do not rotate keys for active subscriptions.')
private = ec.generate_private_key(ec.SECP256R1())
encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip('=')
private_value = encode(private.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
public_value = encode(private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
for key, value in [('PRIVATE_KEY', private_value), ('PUBLIC_KEY', public_value), ('SUBJECT', subject)]:
    set_key(str(path), 'EDOCUMENTS_WEBPUSH_' + key, value)
print('VAPID keys saved to .env. Restart the backend. No private key was printed.')
