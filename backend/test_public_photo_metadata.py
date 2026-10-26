import io
import time

import pytest
from PIL import Image, TiffImagePlugin
from botocore.response import StreamingBody
from backend import images, external_shares
from backend.test_storage import app_client, s3, put_params
from backend.test_photo_location import photo
from backend.test_folder_archive import folder, upload
from backend.test_external_shares import create_link
from backend.test_access import login, ADMIN


def tagged(exposure=None):
    rational = TiffImagePlugin.IFDRational
    with Image.open(io.BytesIO(photo())) as source:
        exif = source.getexif()
        exif[271] = 'Example Camera'
        exif[272] = 'Model 1'
        exif[274] = 6
        exif[315] = 'Private author'
        exif[34665] = {36867: '2026:10:26 10:00:00', 33434: exposure or rational(1, 125),
                       33437: rational(28, 10), 34855: 200, 37386: rational(35),
                       42036: '35 mm lens', 42033: 'Private serial', 37500: b'Private maker note'}
        output = io.BytesIO()
        source.save(output, 'JPEG', exif=exif)
        return output.getvalue()


def test_photographic_metadata_formats_values_and_applies_exif_orientation():
    result = images.public_metadata(tagged())
    assert (result['width'], result['height'], result['format'], result['mode']) == (12, 16, 'JPEG', 'RGB')
    fields = {tag['name']: tag['value'] for tag in result['tags']}
    assert fields['Producent aparatu'] == 'Example Camera'
    assert fields['Model aparatu'] == 'Model 1'
    assert fields['ISO'] == '200'
    assert fields['Czas naświetlania'] == '1/125 s'
    assert fields['Przysłona'] == 'f/2.8'
    assert fields['Ogniskowa'] == '35 mm'
    assert result['location'] == pytest.approx({'latitude': 52.23, 'longitude': 21.01})
    assert 'Private' not in str(result)
    assert images.public_metadata(tagged(TiffImagePlugin.IFDRational(4, 5)))['tags'][4]['value'] == '0.8 s'


def test_photos_without_exif_keep_real_geometry_and_no_invented_tags():
    result = images.public_metadata(photo(False))
    assert result == {'width': 16, 'height': 12, 'format': 'JPEG', 'mode': 'RGB', 'tags': [], 'location': None}


def test_public_metadata_is_scoped_and_revocable_and_rejects_non_photos(app_client):
    _, client = app_client
    root = folder(client, 'Photos')
    image = upload(client, root, 'photo.jpg', tagged())
    broken = upload(client, root, 'broken.jpg', b'not an image')
    text = upload(client, root, 'notes.txt', b'text')
    outside = upload(client, folder(client, 'Private'), 'outside.jpg', tagged())
    link, base = create_link(client, 'folder', root, 'gallery')
    endpoint = lambda row: base + '/documents/' + row['id'] + '/metadata'
    client.post('/api/logout')
    response = client.get(endpoint(image))
    assert response.status_code == 200 and response.json()['width'] == 12
    assert 'no-store' in response.headers['cache-control']
    assert not {'user_id', 'object_key', 'object_bucket', 'content', 'rich_content'} & response.json().keys()
    assert client.get(endpoint(outside)).status_code == 404
    assert client.get(endpoint(text)).status_code == 415
    assert client.get(endpoint(broken)).status_code == 415
    login(client, ADMIN)
    client.delete('/api/external-links/' + link['id'])
    assert client.get(endpoint(image)).status_code == 410


@pytest.mark.parametrize('change,expected', [('revoke', 410), ('expire', 410), ('move', 404), ('replace', 409)])
def test_metadata_rechecks_current_scope_and_version_after_remote_io(app_client, monkeypatch, change, expected):
    main, client = app_client
    root = folder(client, 'Photos')
    image = upload(client, root, 'photo.jpg', tagged())
    link, base = create_link(client, 'folder', root, 'gallery')
    original = images.public_metadata
    def changed(data):
        result = original(data)
        with main.db() as con:
            if change == 'revoke': con.execute('UPDATE external_links SET revoked=1 WHERE id=?', (link['id'],))
            elif change == 'expire': con.execute('UPDATE external_links SET expires=? WHERE id=?', (time.time() - 1, link['id']))
            elif change == 'move': con.execute('UPDATE documents SET folder_id=NULL WHERE id=?', (image['id'],))
            else: con.execute('UPDATE documents SET version=version+1 WHERE id=?', (image['id'],))
        return result
    monkeypatch.setattr(external_shares.images, 'public_metadata', changed)
    assert client.get(base + '/documents/' + image['id'] + '/metadata').status_code == expected


def test_metadata_reads_s3_photo_once_and_closes_the_stream(s3):
    main, client, stub = s3
    data = tagged()
    stub.add_response('put_object', {}, put_params(data))
    image = upload(client, folder(client, 'Photos'), 'photo.jpg', data)
    _, base = create_link(client, 'document', image, 'preview')
    with main.db() as con:
        row = con.execute('SELECT object_bucket,object_key FROM documents WHERE id=?', (image['id'],)).fetchone()
    stream = io.BytesIO(data)
    stub.add_response('get_object', {'Body': StreamingBody(stream, len(data))}, {'Bucket': row['object_bucket'], 'Key': row['object_key']})
    response = client.get(base + '/documents/' + image['id'] + '/metadata')
    assert response.status_code == 200 and response.json()['width'] == 12
    assert stream.closed
