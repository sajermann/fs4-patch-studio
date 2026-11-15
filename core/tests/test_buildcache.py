"""fsmod.buildcache: which code an entry's version follows."""
from fsmod import buildcache


def test_code_version_follows_the_modules_a_converter_is_made_of():
    imports = buildcache.fsmod_imports(b'from . import chunk, scanface\nfrom .kit import x\nimport fsmod.dxt\n'
                                       b'from fsmod import crest\nimport os\n')
    assert imports == {'chunk', 'scanface', 'kit', 'dxt', 'crest'}
    face = buildcache.code_version('facework')
    assert face == buildcache.code_version('facework') and face != buildcache.code_version('kit')
    # the face converter does not depend on the builder: changing the builder keeps the cached faces
    assert 'builder' not in buildcache.fsmod_imports(buildcache._source('facework'))


def test_put_does_not_write_an_entry_twice(tmp_path):
    cache = buildcache.BuildCache(str(tmp_path))
    k = buildcache.key('face', 'v1', 1)
    cache.put(k, {'a': b'1'})
    cache.put(k, {'a': b'2'})  # same key = same files: the first stays
    assert cache.get(k) == {'a': b'1'}
