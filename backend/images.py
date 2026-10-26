"""Bounded raster image processing; coordinates follow EXIF display orientation."""
import io
import math
import warnings

from fastapi import HTTPException
from PIL import Image, ImageOps, ExifTags, UnidentifiedImageError
from pydantic import BaseModel, Field

MAX_PIXELS = 40_000_000
EDIT_FORMATS = {'PNG', 'JPEG', 'WEBP', 'BMP'}


def location_from_gps(gps):
    """Read EXIF GPS DMS coordinates, rejecting incomplete or invalid fixes."""
    def coordinate(value, reference, allowed, limit):
        if isinstance(reference, bytes): reference = reference.decode('ascii')
        if not isinstance(reference, str): raise ValueError()
        reference = reference.strip('\x00 ').upper()
        if reference not in allowed or len(value) != 3: raise ValueError()
        degrees, minutes, seconds = map(float, value)
        if (not all(math.isfinite(part) for part in (degrees, minutes, seconds)) or
                not 0 <= degrees <= limit or not 0 <= minutes < 60 or not 0 <= seconds < 60): raise ValueError()
        result = degrees + minutes / 60 + seconds / 3600
        if result > limit: raise ValueError()
        return -result if reference in ('S', 'W') else result
    try:
        if not isinstance(gps, dict) or not gps: return None
        return {'latitude': coordinate(gps[2], gps[1], ('N', 'S'), 90),
                'longitude': coordinate(gps[4], gps[3], ('E', 'W'), 180)}
    except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError, UnicodeError):
        return None


def gps_location(data):
    with open_image(data) as image:
        try: return location_from_gps(image.getexif().get_ifd(34853))
        except (KeyError, TypeError, ValueError, OSError, SyntaxError): return None

class ImageEdit(BaseModel):
    version: int = Field(strict=True, ge=1)
    x: int = Field(strict=True, ge=0)
    y: int = Field(strict=True, ge=0)
    width: int = Field(strict=True, ge=1)
    height: int = Field(strict=True, ge=1)
    output_width: int = Field(strict=True, ge=1, le=10000)
    output_height: int = Field(strict=True, ge=1, le=10000)

def open_image(data):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(data))
        if image.width * image.height > MAX_PIXELS:
            image.close()
            raise HTTPException(413, 'Obraz przekracza limit 40 milionów pikseli.')
        return image
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise HTTPException(413, 'Obraz jest zbyt duży do przetwarzania.')
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(415, 'Nie można odczytać tego formatu obrazu.')

def editable(image):
    return image.format in EDIT_FORMATS and getattr(image, 'n_frames', 1) == 1

def metadata(data):
    with open_image(data) as image:
        exif = image.getexif()
        width, height = image.size
        if exif.get(274) in (5, 6, 7, 8):
            width, height = height, width
        tags = [{'name': 'Format', 'value': image.format}, {'name': 'Tryb koloru', 'value': image.mode}]
        if image.info.get('dpi'):
            tags.append({'name': 'DPI', 'value': str(image.info['dpi'])})
        values = dict(exif)
        for ifd in (34665, 34853):
            try:
                nested = exif.get_ifd(ifd)
                names = ExifTags.GPSTAGS if ifd == 34853 else ExifTags.TAGS
                for key, value in nested.items():
                    if not isinstance(value, bytes):
                        tags.append({'name': ('GPS ' if ifd == 34853 else '') + names.get(key, str(key)), 'value': str(value)[:1000]})
            except (KeyError, ValueError, TypeError, OSError):
                pass
        for key, value in values.items():
            if key not in (34665, 34853) and not isinstance(value, bytes):
                tags.append({'name': ExifTags.TAGS.get(key, str(key)), 'value': str(value)[:1000]})
        return {'width': width, 'height': height, 'supported': editable(image), 'tags': tags,
                'reason': '' if editable(image) else 'Edycja obsługuje pojedyncze obrazy PNG, JPEG, WebP i BMP. Pozostałe formaty i animacje są tylko do odczytu.'}

def transform(data, body):
    with open_image(data) as source:
        if not editable(source):
            raise HTTPException(415, 'Ten format nie obsługuje edycji lub zawiera wiele klatek.')
        image = ImageOps.exif_transpose(source)
        if image.mode == 'P':
            image = image.convert('RGBA' if 'transparency' in image.info else 'RGB')
        if body.x + body.width > image.width or body.y + body.height > image.height:
            raise HTTPException(422, 'Kadr wykracza poza obraz.')
        if body.output_width * body.output_height > MAX_PIXELS:
            raise HTTPException(413, 'Wynik przekracza limit 40 milionów pikseli.')
        result = image.crop((body.x, body.y, body.x + body.width, body.y + body.height))
        result = result.resize((body.output_width, body.output_height), Image.Resampling.LANCZOS)
        options = {}
        if source.format in {'JPEG', 'PNG', 'WEBP', 'TIFF'}:
            exif = image.getexif()
            for key in (256, 257, 40962, 40963):
                if key in exif:
                    del exif[key]
            if 34665 in exif:
                nested = exif.get_ifd(34665)
                nested.pop(40962, None)
                nested.pop(40963, None)
            if exif:
                options['exif'] = exif.tobytes()
            for key in ('icc_profile', 'dpi'):
                if image.info.get(key):
                    options[key] = image.info[key]
        if source.format == 'JPEG':
            result = result.convert('RGB')
            options['quality'] = 95
        if source.format == 'WEBP':
            options['lossless'] = True
        output = io.BytesIO()
        result.save(output, format=source.format, **options)
        return output.getvalue()
