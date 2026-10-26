import io

import pytest
from PIL import Image, TiffImagePlugin
from botocore.response import StreamingBody
from backend import images
from backend.test_storage import app_client, s3, put_params
from backend.test_folder_archive import folder, upload
from backend.test_external_shares import create_link


@pytest.mark.parametrize('gps,expected', [
    ({1: 'N', 2: (52, 13, 48), 3: 'E', 4: (21, 0, 36)}, (52.23, 21.01)),
    ({1: b'S\x00', 2: (33, 51, 36), 3: b'W', 4: (151, 12, 0)}, (-33.86, -151.2)),
    ({1: 'N', 2: (0, 0, 0), 3: 'E', 4: (0, 0, 0)}, (0, 0)),
    ({1: 'N', 2: (90, 0, 0), 3: 'W', 4: (180, 0, 0)}, (90, -180)),
    ({}, None),
    (None, None),
    ([1, 2, 3], None),
    ({1: 'N', 2: (52, 0, 0)}, None),
    ({1: 'X', 2: (52, 0, 0), 3: 'E', 4: (21, 0, 0)}, None),
    ({1: 'N', 2: (90, 0, 1), 3: 'E', 4: (21, 0, 0)}, None),
    ({1: 'N', 2: (52, 60, 0), 3: 'E', 4: (21, 0, 0)}, None),
    ({1: 'N', 2: (-52, 0, 0), 3: 'E', 4: (21, 0, 0)}, None),
    ({1: 'N', 2: (float('nan'), 0, 0), 3: 'E', 4: (21, 0, 0)}, None),
    ({1: 'N', 2: (52, 0, 0), 3: 'E', 4: (float('inf'), 0, 0)}, None),
    ({1: 'N', 2: (52, 0), 3: 'E', 4: (21, 0, 0)}, None),
])
def test_exif_coordinates_require_complete_valid_gps_data(gps, expected):
    result = images.location_from_gps(gps)
    if expected is None: assert result is None
    else:
        assert result['latitude'] == pytest.approx(expected[0])
        assert result['longitude'] == pytest.approx(expected[1])


def photo(with_gps=True):
    output = io.BytesIO()
    exif = Image.Exif()
    if with_gps:
        rational = TiffImagePlugin.IFDRational
        exif[34853] = {1: 'N', 2: tuple(rational(v) for v in (52, 13, 48)),
                       3: 'E', 4: tuple(rational(v) for v in (21, 0, 36)),
                       6: rational(100), 18: 'Private metadata not included in public response'}
    Image.new('RGB', (16, 12), 'blue').save(output, 'JPEG', exif=exif)
    return output.getvalue()


def test_gps_reader_handles_real_exif_and_photos_without_location():
    assert images.gps_location(photo()) == pytest.approx({'latitude': 52.23, 'longitude': 21.01})
    assert images.gps_location(photo(False)) is None


def test_public_photo_location_is_optional_scoped_and_revocable(app_client):
    _, client = app_client
    root = folder(client, 'Photos')
    tagged = upload(client, root, 'gps.jpg', photo())
    ordinary = upload(client, root, 'plain.jpg', photo(False))
    outside = upload(client, folder(client, 'Private'), 'outside.jpg', photo())
    broken = upload(client, root, 'broken.jpg', b'not an image')
    document = upload(client, root, 'notes.txt', b'text')
    link, base = create_link(client, 'folder', root, 'gallery')
    endpoint = lambda row: base + '/documents/' + row['id'] + '/location'
    client.post('/api/logout')
    result = client.get(endpoint(tagged))
    assert result.status_code == 200
    assert result.json() == {'location': pytest.approx({'latitude': 52.23, 'longitude': 21.01})}
    assert 'no-store' in result.headers['cache-control']
    for row in (ordinary, broken, document):
        assert client.get(endpoint(row)).json() == {'location': None}
    assert client.get(endpoint(outside)).status_code == 404
    from backend.test_access import login, ADMIN
    login(client, ADMIN)
    assert client.delete('/api/external-links/' + link['id']).status_code == 204
    assert client.get(endpoint(tagged)).status_code == 410


def test_revocation_during_s3_read_prevents_returning_coordinates(app_client, monkeypatch):
    main, client = app_client
    row = upload(client, folder(client, 'Photos'), 'gps.jpg', photo())
    link, base = create_link(client, 'document', row, 'preview')
    # Simulate revocation while the remote image metadata is being decoded.
    from backend import external_shares
    original = external_shares.images.gps_location
    def revoke_before_return(data):
        with main.db() as con: con.execute('UPDATE external_links SET revoked=1 WHERE id=?', (link['id'],))
        return original(data)
    monkeypatch.setattr(external_shares.images, 'gps_location', revoke_before_return)
    assert client.get(base + '/documents/' + row['id'] + '/location').status_code == 410


def test_public_gps_metadata_reads_s3_file_and_closes_the_stream(s3):
    main, client, stub = s3
    data = photo()
    stub.add_response('put_object', {}, put_params(data))
    row = upload(client, folder(client, 'Photos'), 'photo.jpg', data)
    link, base = create_link(client, 'document', row, 'preview')
    with main.db() as con:
        stored = con.execute('SELECT object_bucket,object_key FROM documents WHERE id=?', (row['id'],)).fetchone()
    raw = io.BytesIO(data)
    stub.add_response('get_object', {'Body': StreamingBody(raw, len(data))},
                      {'Bucket': stored['object_bucket'], 'Key': stored['object_key']})
    response = client.get(base + '/documents/' + row['id'] + '/location')
    assert response.status_code == 200, response.text
    assert response.json()['location'] == pytest.approx({'latitude': 52.23, 'longitude': 21.01})
    assert raw.closed
