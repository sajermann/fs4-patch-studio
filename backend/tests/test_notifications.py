import json

from fsapi import settings
from fsapi.notifications import NewNotification, NotificationStore, Selection


def add(client, title, kind='info', **extra):
    r = client.post('/api/notifications', json={'kind': kind, 'title': title, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_store_survives_reopening(tmp_path):
    path = tmp_path / 'notifications.json'
    store = NotificationStore(str(path))
    first = store.add(NewNotification(kind='error', title='Build failed', description='face 1', entity='u1'), 'en')
    assert first['id'] == 1 and first['language'] == 'en' and not first['read']
    again = NotificationStore(str(path))
    page = again.page()
    assert page['total'] == 1 and page['unread'] == 1
    assert page['items'][0]['description'] == 'face 1' and page['items'][0]['entity'] == 'u1'
    assert again.add(NewNotification(title='next'))['id'] == 2


def test_store_opens_older_files_and_keeps_broken_ones_aside(tmp_path):
    path = tmp_path / 'notifications.json'
    # a file without the fields added later (version, next_id, language, entity)
    path.write_text(json.dumps({'items': [{'id': 7, 'kind': 'success', 'title': 'ok',
                                           'created_at': '2026-11-12T10:00:00-03:00'}]}), encoding='utf-8')
    store = NotificationStore(str(path))
    assert store.page()['items'][0]['id'] == 7
    assert store.add(NewNotification(title='new'))['id'] == 8
    saved = json.loads(path.read_text(encoding='utf-8'))
    assert saved['version'] == 1 and len(saved['items']) == 2

    path.write_text('{broken', encoding='utf-8')
    store = NotificationStore(str(path))
    assert store.page()['total'] == 0
    assert list(tmp_path.glob('notifications.broken-*.json'))


def test_selection_all_pages_with_exclusions(tmp_path):
    store = NotificationStore(str(tmp_path / 'n.json'))
    for i in range(5):
        store.add(NewNotification(kind='error' if i % 2 else 'success', title=str(i)))
    assert store.mark(Selection(all=True, kind='success', exclude=[1]), True) == 2  # ids 3 and 5
    assert store.page(state='read')['total'] == 2
    assert store.delete(Selection(all=True, state='unread')) == 3
    assert [n['id'] for n in store.page()['items']] == [5, 3]


def test_api_pages_newest_first_and_filters(env):
    client = env['client']
    for i in range(7):
        add(client, f'n{i}', kind='error' if i < 3 else 'success')
    r = client.get('/api/notifications', params={'offset': 0, 'limit': 5}).json()
    assert r['total'] == 7 and r['unread'] == 7
    assert [n['title'] for n in r['items']] == ['n6', 'n5', 'n4', 'n3', 'n2']
    r = client.get('/api/notifications', params={'offset': 5, 'limit': 5}).json()
    assert [n['title'] for n in r['items']] == ['n1', 'n0']
    r = client.get('/api/notifications', params={'kind': 'error'}).json()
    assert r['total'] == 3
    assert client.get('/api/notifications', params={'kind': 'nope'}).status_code == 422


def test_api_read_unread_delete(env):
    client = env['client']
    ids = [add(client, f'n{i}')['id'] for i in range(4)]
    r = client.post('/api/notifications/read', json={'ids': ids[:2]}).json()
    assert r == {'changed': 2, 'unread': 2}
    r = client.get('/api/notifications', params={'state': 'unread', 'limit': 5}).json()
    assert [n['id'] for n in r['items']] == [ids[3], ids[2]]
    r = client.post('/api/notifications/read', params={'read': 'false'}, json={'ids': [ids[0]]}).json()
    assert r['unread'] == 3
    assert client.get(f'/api/notifications/{ids[1]}').json()['read'] is True
    r = client.post('/api/notifications/delete', json={'all': True, 'exclude': [ids[2]]}).json()
    assert r == {'deleted': 3, 'unread': 1}
    assert client.get(f'/api/notifications/{ids[0]}').status_code == 404


def test_language_is_kept_in_the_config_and_written_in_new_notifications(env):
    client, state = env['client'], env['state']
    assert client.get('/api/config').json()['language'] is None
    assert client.put('/api/config/language', json={'language': 'en'}).json()['language'] == 'en'
    assert settings.load_config(state.config_path).language == 'en'
    assert add(client, 'a')['language'] == 'en'
    # the settings screen sends back the config it loaded (older language): the language is not overwritten
    config = client.get('/api/config').json()
    config['language'] = 'pt-BR'
    assert client.put('/api/config', json=config).json()['language'] == 'en'
    client.put('/api/config/language', json={'language': 'pt-BR'})
    assert add(client, 'b')['language'] == 'pt-BR'
    assert add(client, 'c', language='en')['language'] == 'en'  # what the UI says wins
    assert client.put('/api/config/language', json={'language': 'xx'}).status_code == 422


def test_config_with_unknown_language_still_loads(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'project_dir': str(tmp_path), 'language': 'fr'}), encoding='utf-8')
    assert settings.load_config(str(path)).language is None
