from fsmod import model, weblink


def test_only_web_addresses_are_kept():
    assert weblink.normalize('https://soccergaming.com/x') == 'https://soccergaming.com/x'
    assert weblink.normalize(' http://a.org ') == 'http://a.org'
    assert weblink.normalize('www.site.com/path?a=1') == 'https://www.site.com/path?a=1'
    assert weblink.normalize('site.com:8080/a') == 'https://site.com:8080/a'
    for bad in ('', '   ', None, 3, 'javascript:alert(1)', 'file:///C:/x', 'mailto:a@b.com', 'ftp://a.org',
                'https://', 'hello', 'http://a b.com'):
        assert weblink.normalize(bad) is None, bad


def test_scanned_face_keeps_what_the_manifest_said():
    face = model.ScannedFace(source_id=1, name='Ana', credits='Colgado', credits_url='colgado.com')
    assert face.credits_url == 'https://colgado.com'
    assert model.ScannedFace(source_id=1, credits_url='javascript:x').credits_url is None
    old = model.ScannedFace.model_validate({'source_id': 1, 'pack': 'p'})  # saved before 12/11/2026
    assert (old.name, old.credits, old.credits_url) == (None, None, None)
