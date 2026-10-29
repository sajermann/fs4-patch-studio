import filecmp
import json
import os
import shutil

import pytest

from conftest import FIXTURES, REFERENCE
from fsmod import builder, chunk, model

PALMEIRAS = os.path.join(FIXTURES, 'palmeiras')


def load_palmeiras():
    with open(os.path.join(PALMEIRAS, 'project_v1.json'), encoding='utf-8') as f:
        return model.from_v1(json.load(f))


@pytest.fixture(scope='module')
def palmeiras_result(game):
    return builder.build(load_palmeiras(), game, PALMEIRAS)


@pytest.fixture(scope='module')
def palmeiras_patch(game, palmeiras_result, tmp_path_factory):
    return builder.write_patch(palmeiras_result, game, str(tmp_path_factory.mktemp('patch')))


def read(path):
    with open(path, 'rb') as f:
        return f.read()


def read_range(path, offset, size):
    with open(path, 'rb') as f:
        f.seek(offset)
        return f.read(size)


def patched_entry(archive, name):
    """(offset, size, bytes) of an entry read through the archive's BIG4 header; checks the .bh agrees."""
    from fsmod import big
    toc, _ = big.read_toc_positions(archive)
    _, offset, size = toc[name]
    index = archive[:-4] + '.bh'
    if os.path.exists(index):
        entries = big.read_bh_entries(read(index))
        assert (offset, size) in {(o, s) for o, s, _, h in entries if h == big.djb2(name.encode())}, name
    return offset, size, read_range(archive, offset, size)


def dds_size(entry):
    import io
    from PIL import Image
    from fsmod import chunk
    return Image.open(io.BytesIO(chunk.decode(entry))).size


def palmeiras_team_id(result):
    return next(iter(result.assigned_team_ids.values()))


def test_palmeiras_build_matches_the_files_validated_in_game(game, palmeiras_result):
    """Validated in game on ReStreet 1.2 (19/10/2026) in slot 1932 (Mods overlay: byte patches at original offsets).
    The kits and kit thumbnails are now loose files of the new teamid made from slot 1932's kits: same bytes."""
    from fsmod import big
    if not os.path.isdir(REFERENCE):
        pytest.skip('validated reference build not available')
    tid = palmeiras_team_id(palmeiras_result)
    ref_mods = {n: read(os.path.join(REFERENCE, 'Mods', n)) for n in os.listdir(os.path.join(REFERENCE, 'Mods'))}
    assert len(ref_mods) == 8
    checked = 0
    for name, data in ref_mods.items():
        short, offset = name[:-4].split('@')
        offset = int(offset, 16)
        toc, _ = big.read_toc_positions(game.target_path(short))
        entry = next(n for n, (_, o, _) in toc.items() if o == offset)
        if '/crest/' in entry or entry.startswith('data/loc/'):
            continue
        new_name = entry.replace('kit_1932_', f'kit_{tid}_').replace('_01932.dds', f'_{tid:05d}.dds')
        built = palmeiras_result.loose[new_name]
        assert built == data[:len(built)] and not data[len(built):].strip(b'\0'), new_name
        checked += 1
    assert checked == 4  # 2 kits, 2 kit thumbnails


# every file the app can change always goes in the patch (original when unchanged)
FULL_PATCH = [builder.BUILD_STATE, 'Game/data/loc/locale.big', 'Game/data/loc/locale_ptbr.big',
              'Game/data/ui/imgAssets/heads/2dheads.bh', 'Game/data/ui/imgAssets/heads/2dheads.big',
              'Game/data0.bh', 'Game/data0.big', 'Game/data1.bh', 'Game/data1.big', 'Game/data3.bh', 'Game/data3.big',
              'Game/data7.bh', 'Game/data7.big',
              'Game/data8.bh', 'Game/data8.big']


def patch_listing(patch_dir):
    return sorted(os.path.relpath(os.path.join(root, n), patch_dir).replace(os.sep, '/')
                  for root, _, files in os.walk(patch_dir) for n in files)


def test_write_patch_writes_whole_archives_in_the_v2_layout(game, palmeiras_result, palmeiras_patch):
    tid = palmeiras_team_id(palmeiras_result)
    loose = ['Game/' + n for n in palmeiras_result.loose]
    assert sorted(map(str.lower, patch_listing(palmeiras_patch))) == sorted(map(str.lower, FULL_PATCH + loose))
    for short in ('data0.big', 'data1.big', 'data3.big', 'data7.big', '2dheads.big'):  # only loose files: originals
        for path in (game.target_path(short), game.index_path(short)):
            rel = os.path.relpath(path, os.path.join(game.folder, 'Game'))
            assert filecmp.cmp(os.path.join(palmeiras_patch, 'Game', rel), path, shallow=False), rel
    for (short, name), data in palmeiras_result.entries.items():
        archive = os.path.join(palmeiras_patch, 'Game', builder.PATCH_TARGETS[short])
        offset, size, stored = patched_entry(archive, name)
        assert stored[:len(data)] == data, name
        if offset < os.path.getsize(game.target_path(short)):
            assert stored[len(data):] == bytes(size - len(data)), name  # in place: zero padded
        else:
            assert size == len(data), name  # moved to the end
    assert f'data/sceneassets/kit/kit_{tid}_0_0.rx3' in palmeiras_result.loose


def test_menu_crests_are_loose_files_twice_the_original_size(game, palmeiras_result, palmeiras_patch):
    from fsmod import crest
    tid = palmeiras_team_id(palmeiras_result)
    assert not game.locate(crest.ui_crest_name('large', tid))
    for label, px in crest.UI_SIZES:
        stored = read(os.path.join(palmeiras_patch, 'Game', *crest.ui_crest_name(label, tid).split('/')))
        assert dds_size(stored) == (px * crest.SCALE, px * crest.SCALE)


def test_write_patch_reuses_archives_and_restores_old_entries(game, palmeiras_result, tmp_path, monkeypatch):
    """Entries replacing files of the archives (here: slot 1932's crests and away kit, as the old slot teams
    did) are written in place or moved to the end; dropped ones go back to the original."""
    import shutil
    from fsmod import crest
    tid = palmeiras_team_id(palmeiras_result)
    crests = {('data1.big', crest.ui_crest_name(label, 1932)): palmeiras_result.loose[crest.ui_crest_name(label, tid)]
              for label, _ in crest.UI_SIZES}
    away = ('data3.big', 'data/sceneassets/kit/kit_1932_1_0.rx3')
    first = builder.BuildResult(database=palmeiras_result.database, entries={
        **palmeiras_result.entries, **crests, away: palmeiras_result.loose[f'data/sceneassets/kit/kit_{tid}_1_0.rx3']})
    out = str(tmp_path / 'patch')
    builder.write_patch(first, game, out)
    for key, data in crests.items():
        offset, _, stored = patched_entry(os.path.join(out, 'Game', 'data1.big'), key[1])
        assert offset >= os.path.getsize(game.target_path('data1.big')) and stored == data  # bigger: moved
    os.makedirs(os.path.join(out, 'Mods'))  # leftovers of the ReStreet 1.x layout are removed
    copies = []
    real_copy = shutil.copyfile
    monkeypatch.setattr(shutil, 'copyfile', lambda src, dst: copies.append(src) or real_copy(src, dst))
    # second build: no crests, no away kit -> those entries go back to the original
    second = builder.BuildResult(database=palmeiras_result.database, entries=dict(palmeiras_result.entries))
    builder.write_patch(second, game, out)
    assert copies == []  # archives reused, not copied again
    assert 'Mods' not in os.listdir(out)
    assert read(os.path.join(out, 'Game', 'data1.bh')) == read(game.index_path('data1.big'))  # nothing moved
    for key in set(crests) | {away}:
        short, name = key
        k, offset, original = game.read_entry(name)
        assert patched_entry(os.path.join(out, 'Game', short), name) == (offset, len(original), original), name
    assert patch_listing(out) == FULL_PATCH
    for short in ('data1.big', 'data3.big'):
        assert filecmp.cmp(os.path.join(out, 'Game', short), game.target_path(short), shallow=False), short


def test_ptbr_locale_gets_the_same_texts(game, palmeiras_result):
    """ReStreet 2.x reads locale_ptbr.big instead of locale.big when the launcher language is pt-BR."""
    from fsmod import locale, t3db
    from fsmod.game import LOCALE_ENTRY, LOCALE_PTBR_FILE
    tid = palmeiras_team_id(palmeiras_result)
    original = game.locale(LOCALE_PTBR_FILE)[1]
    new = palmeiras_result.entries['locale_ptbr.big', LOCALE_ENTRY]
    english = locale.texts(palmeiras_result.entries['locale.big', LOCALE_ENTRY])
    texts, before = locale.texts(new), locale.texts(original)
    lid = next(iter(palmeiras_result.assigned_league_ids.values()))
    for key in (f'TeamName_{tid}', f'TeamName_Abbr3_{tid}', f'LeagueName_{lid}'):
        assert texts[key] == english[key] != before.get(key), key
    assert texts['LeagueName_13'] == before['LeagueName_13'] == 'Primeira Liga Barclays'  # pt-BR texts kept
    db = t3db.Database(new)
    assert locale.strings_table(db).shared_strings and locale.strings_table(db).huff.exact_padding


def test_clean_removes_faint_pixels_and_bleeds_edge_color():
    from PIL import Image
    from fsmod import imageprep
    img = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
    for x in range(8, 24):
        for y in range(8, 24):
            img.putpixel((x, y), (200, 40, 40, 255))
    img.putpixel((2, 2), (255, 255, 255, 10))  # stray pixel left by a background remover
    out = imageprep.clean(img)
    assert out.getpixel((2, 2))[3] == 0
    assert out.getpixel((10, 10)) == (200, 40, 40, 255)  # visible pixels untouched
    r, g, b, a = out.getpixel((4, 16))  # transparent, takes the color of the subject
    assert a == 0 and r > 150 and g < 80


def test_v1_conversion():
    project = load_palmeiras()
    assert [lg.name for lg in project.leagues] == ['Brasileirão']
    team = project.teams[0]
    assert team.league == project.leagues[0].uid
    assert len(project.roster(team.uid)) == 10
    assert team.captain == project.roster(team.uid)[0].uid
    assert team.kit('away').jersey == (245, 245, 245)


def test_rejects_hidden_league(game):
    project = load_palmeiras()
    project.leagues[0].league_id = 382
    with pytest.raises(builder.BuildError) as e:
        builder.build(project, game, PALMEIRAS)
    assert e.value.entity == project.leagues[0].uid


def test_rejects_roster_over_13(game):
    project = load_palmeiras()
    team = project.teams[0]
    extra = project.roster(team.uid)[0]
    for i in range(4):
        project.players.append(model.Player(uid=f'x{i}', team=team.uid, first_name='Extra', last_name=str(i)))
    with pytest.raises(builder.BuildError, match='1 to 13'):
        builder.build(project, game, PALMEIRAS)
    assert extra.team == team.uid


def test_league_team_limit_counts_new_and_original_teams(game):
    from fsmod import validation
    from fsmod.catalog import Catalog
    catalog = Catalog(game)
    project = load_palmeiras()
    new_league = project.teams[0].league
    copies = [project.teams[0].model_copy(update={'uid': f'tm_{k}', 'team_id': None})
              for k in range(builder.MAX_LEAGUE_TEAMS)]
    project.teams += copies

    def codes():
        return sorted({(i.entity, i.params['count']) for i in validation.validate(project, catalog, PALMEIRAS)
                       if i.code == 'league_too_many_teams'})
    assert (new_league, builder.MAX_LEAGUE_TEAMS + 1) in codes()
    project.teams.pop()
    assert codes() == []
    # original league (MLS, 18 teams): the project teams add up; teams the project hides do not count
    mls = [t['id'] for t in catalog.teams if t['league'] == 39]
    for t in copies[:13]:
        t.league = 39
    assert ('tm_0', len(mls) + 13) in codes()
    project.originals.hidden_teams = mls[:1]
    assert codes() == []


def test_rejects_characters_missing_from_the_huffman_tree(game):
    project = load_palmeiras()
    project.players[0].last_name = 'Silva中'
    with pytest.raises(builder.BuildError) as e:
        builder.build(project, game, PALMEIRAS)
    assert e.value.entity == project.players[0].uid


def test_team_texts_are_new_locale_keys(game):
    """A new team's names are new locale keys (hash = locale.key_hash, rows kept in hash order); nothing else
    changes but the project's own texts."""
    from fsmod import locale, t3db
    from fsmod.game import LOCALE_ENTRY
    project = load_palmeiras()
    team = project.teams[0]
    long_name = 'Sociedade Esportiva Teste da Silva'
    team.name = team.short_name = long_name
    team.name_10 = team.name_7 = None
    result = builder.build(project, game, PALMEIRAS)
    tid = result.assigned_team_ids[team.uid]
    original, new = game.locale()[1], result.entries['locale.big', LOCALE_ENTRY]
    texts, before = locale.texts(new), locale.texts(original)
    own = {f'CT_TeamName_{tid}'} | {k.format(tid) for k in builder.TEAM_TEXT_KEYS.values()}
    assert not own & set(before)
    assert texts[f'TeamName_{tid}'] == texts[f'TeamName_Abbr15_{tid}'] == long_name
    lid = result.assigned_league_ids[project.leagues[0].uid]
    assert {k for k in texts if texts[k] != before.get(k)} == own | {f'LeagueName_{lid}', f'LeagueName_Abbr15_{lid}'}
    def descents(data):  # the original already has 12 rows out of hash order
        rows = locale.strings_table(t3db.Database(data)).records
        return sum(b[2] < a[2] for a, b in zip(rows, rows[1:]))
    assert descents(new) == descents(original)
    rows = locale.strings_table(t3db.Database(new)).records
    assert all(locale.key_hash(r[0]) == r[2] for r in rows if r[0].decode() in own)


def test_locale_key_hash_matches_the_game(game):
    """The keys it misses have non-ASCII characters."""
    from fsmod import locale, t3db
    rows = locale.strings_table(t3db.Database(game.locale()[1])).records
    missed = [r[0] for r in rows if locale.key_hash(r[0]) != r[2]]
    assert len(missed) == 26 and len(rows) == 21077
    assert locale.key_hash(b'TeamName_1932') == 0x4718827D


def test_team_ids_are_new_stable_and_validated(game):
    from fsmod import validation
    from fsmod.catalog import Catalog
    project = load_palmeiras()
    first = project.teams[0]
    second = first.model_copy(update={'uid': 'tm_02', 'name': 'Outro', 'team_id': 200000})
    project.teams.append(second)
    project.players.append(project.players[0].model_copy(update={'uid': 'x', 'team': 'tm_02'}))
    result = builder.build(project, game, PALMEIRAS)
    assert result.assigned_team_ids == {first.uid: builder.FIRST_NEW_TEAMID}
    catalog = Catalog(game)
    assert max(i for i in catalog.reserved_team_ids if i < 200000) < builder.FIRST_NEW_TEAMID
    second.team_id = 130000  # has FIFA 12 texts (TeamName_130000), below the new ids
    codes = [(i.code, i.entity) for i in validation.validate(project, catalog, PALMEIRAS) if i.field == 'team_id']
    assert codes == [('team_id_out_of_range', 'tm_02')]
    first.team_id = second.team_id = 150005
    codes = [(i.code, i.entity) for i in validation.validate(project, catalog, PALMEIRAS) if i.field == 'team_id']
    assert codes == [('team_id_taken', 'tm_02')]
    second.crest = None
    assert ('crest_required', 'tm_02') in [(i.code, i.entity) for i in validation.validate(project, catalog, PALMEIRAS)]


def test_player_photos_are_loose_files_named_by_new_playerids(game, tmp_path):
    """A new player's photo is a loose file p<playerid>.dds (the game opens it from disk: entries added to an
    archive are not found), at 2x the original size; 2dheads.big stays original."""
    import shutil
    from PIL import Image
    from fsmod import photo
    from fsmod.game import PHOTOS_FILE
    project = load_palmeiras()
    shutil.copy(os.path.join(PALMEIRAS, 'escudo_palmeiras.png'), tmp_path)
    Image.new('RGBA', (300, 400), (200, 30, 30, 255)).save(tmp_path / 'face.png')
    roster = project.roster(project.teams[0].uid)
    for p in roster[:3]:
        p.photo = 'face.png'
    result = builder.build(project, game, str(tmp_path))
    pids = [result.assigned_player_ids[p.uid] for p in roster[:3]]
    assert not [k for k in result.entries if k[0] == '2dheads.big']
    assert {photo.photo_name(p) for p in pids} <= set(result.loose)
    assert not any(p in game.photo_index for p in pids)
    out = builder.write_patch(result, game, str(tmp_path / 'patch'))
    for pid in pids:
        with open(os.path.join(out, 'Game', *photo.photo_name(pid).split('/')), 'rb') as f:
            assert dds_size(chunk.decode(f.read())) == (photo.SIZE, photo.SIZE)
    with open(os.path.join(out, 'Game', PHOTOS_FILE), 'rb') as f, open(game.target_path('2dheads.big'), 'rb') as g:
        assert f.read() == g.read()


def test_player_ids_are_new_stable_and_validated(game, tmp_path):
    """Every player gets a playerid the game does not use (not a player, photo or head); a stored id is kept."""
    from fsmod import t3db, validation
    from fsmod.catalog import Catalog
    project = load_palmeiras()
    project.players[0].player_id = 300000
    result = builder.build(project, game, PALMEIRAS)
    assert project.players[0].uid not in result.assigned_player_ids
    reserved = Catalog(game).reserved_player_ids
    given = list(result.assigned_player_ids.values())
    assert len(set(given)) == len(project.players) - 1 and not set(given) & reserved
    assert min(given) == builder.FIRST_NEW_PLAYERID
    db = t3db.Database(result.database, game.meta)
    players = db.by_name('players')
    assert {300000, *given} <= {players.value(r, players.field('playerid')) for r in players.records}

    catalog = Catalog(game)
    project.players[1].player_id = 300000  # same as players[0]
    project.players[2].player_id = 1000
    codes = [(i.code, i.entity) for i in validation.validate(project, catalog, PALMEIRAS) if i.field == 'player_id']
    assert codes == [('player_id_taken', project.players[1].uid), ('player_id_out_of_range', project.players[2].uid)]
    assert max(catalog.reserved_player_ids) < builder.FIRST_NEW_PLAYERID


def test_template_sources_match_what_the_builder_copies(game):
    """The UI shows inherited values from catalog.player_defaults; they must be what the build really writes."""
    from fsmod import t3db
    from fsmod.catalog import Catalog
    project = load_palmeiras()
    for p in project.players:  # nothing set: every bar comes from the template
        p.skills = {}
        p.height = None
    defaults = Catalog(game).player_defaults(project)
    result = builder.build(project, game, PALMEIRAS)
    db = t3db.Database(result.database, game.meta)
    players = db.by_name('players')
    built = {players.value(r, players.field('playerid')): r for r in players.records}
    first_new = min(pid for pid in built if pid >= builder.FIRST_NEW_PLAYERID)
    for k, p in enumerate(project.roster(project.teams[0].uid)):
        row = built[first_new + k]
        d = defaults[p.uid]
        assert players.value(row, players.field('fsathleticism')) == d['skills']['ATH']
        assert players.value(row, players.field('height')) == d['height']


def test_street_kit_pieces_fill_every_teamkits_slot(game):
    """A chosen street piece goes to all of its teamkits slots (the game picks one at random) with its 3
    colors; parts left unset keep the template's pieces."""
    from fsmod import t3db
    project = load_palmeiras()
    team = project.teams[0]
    team.street_kits = {'away': model.StreetKit(top=model.StreetPart(style=24, pattern=3,
                                                                     colors=[(1, 2, 3), (4, 5, 6), (7, 8, 9)]))}
    result = builder.build(project, game, PALMEIRAS)
    db = t3db.Database(result.database, game.meta)
    kits = db.by_name('teamkits')
    get = lambda r, f: kits.value(r, kits.field(f))
    tid = result.assigned_team_ids[team.uid]
    rows = {get(r, 'teamkittypetechid'): r for r in kits.records if get(r, 'teamtechid') == tid}
    away, home = rows[1], rows[0]
    assert [get(away, f'top_geo_type_{n}') for n in range(1, 6)] == [24] * 5
    assert [get(away, f'top_texture_pattern_{n}') for n in range(1, 6)] == [3] * 5
    assert [get(away, f'top_color_tertiary_{c}') for c in 'rgb'] == [7, 8, 9]
    assert get(away, 'bottom_geo_type_1') == 0 and get(home, 'top_geo_type_1') == 20  # template pieces kept


def test_write_patch_takes_data7_entries_and_reuses_the_archive(game, palmeiras_result, tmp_path, monkeypatch):
    """The far hair of scanned faces (hairlod) lives in data7: a bigger entry moves to the end and data7.bh follows."""
    from fsmod import big
    name = next(n for n, _, _ in big.read_toc_file(game.target_path('data7.big')) if '/hairlod/' in n)
    k, offset, original = game.read_entry(name)
    grown = original + bytes(0x100)
    out = str(tmp_path / 'patch')
    entries = {**palmeiras_result.entries, ('data7.big', name): grown}
    builder.write_patch(builder.BuildResult(database=palmeiras_result.database, entries=entries), game, out)
    archive = os.path.join(out, 'Game', 'data7.big')
    assert patched_entry(archive, name)[1:] == (len(grown), grown)
    assert os.path.exists(os.path.join(out, 'Game', 'data7.bh'))
    copies = []
    real_copy = shutil.copyfile
    monkeypatch.setattr(shutil, 'copyfile', lambda src, dst: copies.append(src) or real_copy(src, dst))
    entries[('data7.big', name)] = original[:len(original) // 2]  # fits in place now
    builder.write_patch(builder.BuildResult(database=palmeiras_result.database, entries=entries), game, out)
    assert copies == []
    assert read(os.path.join(out, 'Game', 'data7.bh')) == read(game.index_path('data7.big'))
    assert os.path.getsize(archive) == os.path.getsize(game.target_path('data7.big'))
    assert patched_entry(archive, name) == (offset, len(original), original[:len(original) // 2] +
                                            bytes(len(original) - len(original) // 2))


def test_league_is_new_with_its_own_texts_and_referees(game):
    """A new league takes a leagueid the game does not know (no texts, not hidden by any screen), gets new locale
    keys and the template league's referees."""
    from fsmod import locale, t3db, validation
    from fsmod.catalog import Catalog
    project = load_palmeiras()
    result = builder.build(project, game, PALMEIRAS)
    lid = result.assigned_league_ids[project.leagues[0].uid]
    assert lid == builder.FIRST_NEW_LEAGUEID
    catalog = Catalog(game)
    assert max(catalog.reserved_league_ids) < builder.FIRST_NEW_LEAGUEID
    db = builder.Db(result.database, game.meta)
    assert len(db.rows('leagues', 'leagueid', lid)) == 1
    assert len(db.rows('leaguerefereelinks', 'leagueid', lid)) == len(
        db.rows('leaguerefereelinks', 'leagueid', builder.TEMPLATE_LEAGUE)) == 4
    tid = result.assigned_team_ids[project.teams[0].uid]
    assert db.get(db.table('leagueteamlinks'), db.table('leagueteamlinks').records[
        db.rows('leagueteamlinks', 'teamid', tid)[0]], 'leagueid') == lid
    assert f'LeagueName_{lid}' not in locale.keys(game.locale()[1])
    project.leagues[0].league_id = 100
    codes = [i.code for i in validation.validate(project, catalog, PALMEIRAS) if i.field == 'league_id']
    assert codes == ['league_id_out_of_range']


def test_texts_go_to_every_language_of_both_locale_files(game, palmeiras_result):
    """Each locale file has 5 languages with the same keys; the game shows the one of the launcher language."""
    from fsmod import locale
    from fsmod.game import LOCALE_ENTRIES
    tid = palmeiras_team_id(palmeiras_result)
    name = palmeiras_result.assigned_team_ids and load_palmeiras().teams[0].name
    for short in ('locale.big', 'locale_ptbr.big'):
        for entry in LOCALE_ENTRIES:
            texts = locale.texts(palmeiras_result.entries[short, entry])
            assert texts[f'TeamName_{tid}'] == name, (short, entry)


def test_original_leagues_and_teams_hidden_and_unlockables_set(game):
    """project.originals (validated in game): hidden leagues/teams move to league 2095, which the
    selector hides; locks change the game's own fs4unlockables_defs rows."""
    from fsmod import validation
    from fsmod.catalog import Catalog
    project = load_palmeiras()
    project.originals = model.OriginalChanges(hidden_leagues=[39], hidden_teams=[243], team_locks={112339: False},
                                              stadium_locks={1117: False})
    result = builder.build(project, game, PALMEIRAS)
    db = builder.Db(result.database, game.meta)
    links, defs = db.table('leagueteamlinks'), db.table('fs4unlockables_defs')
    league_of = {db.get(links, r, 'teamid'): db.get(links, r, 'leagueid') for r in links.records}
    assert not db.rows('leagues', 'leagueid', 39)
    assert league_of[243] == league_of[687] == builder.HIDDEN_TEAMS_LEAGUE  # Real Madrid, an MLS team
    assert league_of[241] == 53
    locked = {(db.get(defs, r, 'type_id'), db.get(defs, r, 'item_id')): db.get(defs, r, 'is_locked') for r in defs.records}
    assert locked[3, 112339] == 0 and locked[3, 112338] == 1 and locked[2, 1117] == 0 and locked[2, 1118] == 1
    tid = result.assigned_team_ids[project.teams[0].uid]
    assert league_of[tid] == result.assigned_league_ids[project.leagues[0].uid]  # new league built from MLS: fine

    catalog = Catalog(game)
    project.originals = model.OriginalChanges(hidden_leagues=[382, 7], hidden_teams=[5], team_locks={241: True},
                                              stadium_locks={1: True})
    codes = [(i.code, i.params.get('id')) for i in validation.validate(project, catalog, PALMEIRAS)
             if i.field and i.field.startswith('originals')]
    assert codes == [('original_league_not_hideable', 382), ('original_league_not_hideable', 7),
                     ('original_team_not_lockable', 241), ('stadium_not_lockable', 1)]
    with pytest.raises(builder.BuildError, match='cannot be locked'):
        project.originals = model.OriginalChanges(team_locks={241: True})
        builder.build(project, game, PALMEIRAS)


def test_hidden_project_leagues_and_teams_are_left_out(game):
    """A hidden league leaves the patch with its teams, a hidden team with its players; nothing hidden is
    validated, and the ids they already have are not given to anyone else."""
    from fsmod import validation
    from fsmod.catalog import Catalog
    project = load_palmeiras()
    team = project.teams[0]
    other = team.model_copy(update={'uid': 'tm_02', 'name': 'Inacabado', 'crest': None, 'team_id': 150000,
                                    'hidden': True})
    project.teams.append(other)
    project.players.append(project.players[0].model_copy(update={'uid': 'x', 'team': 'tm_02', 'player_id': 206656}))
    result = builder.build(project, game, PALMEIRAS)
    db = builder.Db(result.database, game.meta)
    assert result.assigned_team_ids == {team.uid: 150001}  # 150000 stays with the hidden team
    assert not db.rows('teams', 'teamid', 150000) and db.rows('teams', 'teamid', 150001)
    assert 206656 not in result.assigned_player_ids.values() and not db.rows('players', 'playerid', 206656)
    issues = validation.validate(project, Catalog(game), PALMEIRAS)
    assert not [i for i in issues if i.entity in ('tm_02', 'x')]  # no crest: would be an error if visible

    hidden_player = project.roster(team.uid)[0].model_copy(update={'uid': 'y', 'player_id': 206700, 'hidden': True,
                                                                    'first_name': ''})
    project.players.append(hidden_player)
    result = builder.build(project, game, PALMEIRAS)
    assert 206700 not in result.assigned_player_ids.values()
    assert not builder.Db(result.database, game.meta).rows('players', 'playerid', 206700)
    assert not [i for i in validation.validate(project, Catalog(game), PALMEIRAS) if i.entity == 'y']

    project.leagues[0].hidden = True  # the league and its only visible team leave the patch
    result = builder.build(project, game, PALMEIRAS)
    assert result.assigned_league_ids == {} and result.assigned_team_ids == {}
    db = builder.Db(result.database, game.meta)
    assert not db.rows('teams', 'teamid', 150001)


def test_real_kits_go_as_loose_files_with_their_teamkits_fields(game, tmp_path):
    """Real kits (FIFA 14-16 PNGs): kit rx3 with the PNGs, the default position table and a
    transparent crest_cm; teamkits fields of the slot; a goalkeeper row (type 2) only when that slot is used."""
    import struct
    from PIL import Image
    from fsmod import kit, rx3tex, t3db
    paths = {}
    for name, size, color in (('jersey', (256, 256), (22, 76, 50)), ('shorts', (256, 128), (240, 240, 240)),
                              ('gk_jersey', (128, 128), (230, 240, 40)), ('gk_shorts', (128, 64), (230, 240, 40))):
        paths[name] = str(tmp_path / f'{name}.png')
        Image.new('RGB', size, color).save(paths[name])
    project = load_palmeiras()
    team = project.teams[0]
    team.use_real_kits = True
    team.real_kits = {
        'home': model.RealKit(jersey=paths['jersey'], shorts=paths['shorts'], name_color=(1, 2, 3), number_color=19,
                              shorts_number_color=2, collar=8),
        'away': model.RealKit(jersey=paths['jersey']),  # incomplete: generic kit
        'goalkeeper': model.RealKit(jersey=paths['gk_jersey'], shorts=paths['gk_shorts'], number_color=6),
    }
    result = builder.build(project, game, PALMEIRAS)
    tid = result.assigned_team_ids[team.uid]
    for kind in (0, 1, 2):
        assert kit.kit_name(tid, kind) in result.loose and kit.thumbnail_name(tid, kind) in result.loose

    d = chunk.decode(result.loose[kit.kit_name(tid, 0)])
    jersey = rx3tex.to_image(d, rx3tex.by_name(d, 'jersey_cm')).convert('RGB')
    assert all(abs(a - b) <= 8 for a, b in zip(jersey.getpixel((500, 500)), (22, 76, 50)))
    assert rx3tex.to_image(d, rx3tex.by_name(d, 'crest_cm')).getextrema()[3] == (0, 0)
    values = [struct.unpack('>4f', d[p:p + 16]) for _, p in kit._positions(d)]
    assert values == [pytest.approx(v) for _, v in kit.REAL_POSITIONS]
    away = chunk.decode(result.loose[kit.kit_name(tid, 1)])
    assert rx3tex.by_name(away, 'crest_cm')  # generic kit (solid color + crest)

    db = t3db.Database(result.database, game.meta)
    kits = db.by_name('teamkits')
    get = lambda r, f: kits.value(r, kits.field(f))
    rows = {get(r, 'teamkittypetechid'): r for r in kits.records if get(r, 'teamtechid') == tid}
    assert sorted(rows) == [0, 1, 2]
    home, away_row, gk = rows[0], rows[1], rows[2]
    assert [get(home, f'jerseynamecolor{c}') for c in 'rgb'] == [1, 2, 3]
    assert (get(home, 'numbercolor'), get(home, 'shortsnumbercolor'), get(home, 'jerseycollargeometrytype'),
            get(home, 'jerseyfrontnumberplacementcode')) == (19, 2, 8, 0)
    assert get(away_row, 'jerseyfrontnumberplacementcode') == 1  # generic: the template's
    assert (get(gk, 'numbercolor'), get(gk, 'jerseycollargeometrytype')) == (6, 0)
    assert len({get(r, 'teamkitid') for r in rows.values()}) == 3

    team.use_real_kits = False  # switched back to generic: real kits kept in the project, not built
    result = builder.build(project, game, PALMEIRAS)
    assert kit.kit_name(result.assigned_team_ids[team.uid], 2) not in result.loose


def test_lineup_order_fills_empty_slots_and_skips_players_out_of_the_team():
    roster = ['a', 'b', 'c', 'd', 'e', 'f']
    lineup = model.Lineup(players=5, goalkeeper=True, starters=['c', None, 'gone', 'a', 'c'], reserves=['f'])
    # empty, missing and repeated slots take the reserves first, then roster order; the rest is the bench
    assert builder.lineup_order(lineup, roster) == ['c', 'f', 'b', 'a', 'd', 'e']
    assert builder.lineup_order(model.Lineup(players=2, goalkeeper=False), ['a']) == ['a']


def test_lineups_go_to_fs4lineup_on_both_sides(game):
    """One fs4lineup row per mode and side, slots in the lineup's order then the bench."""
    from fsmod import catalog as fscatalog, t3db, validation
    project = load_palmeiras()
    team = project.teams[0]
    roster = [p.uid for p in project.roster(team.uid)]
    team.lineups = [model.Lineup(players=5, goalkeeper=True, tactic=0, starters=[roster[3], roster[1]]),
                    model.Lineup(players=2, goalkeeper=False, starters=[roster[2], roster[0]])]
    result = builder.build(project, game, PALMEIRAS)
    db = t3db.Database(result.database, game.meta)
    t = db.by_name('fs4lineup')
    get = lambda r, f: t.value(r, t.field(f))
    pid = result.assigned_player_ids
    tid = result.assigned_team_ids[team.uid]
    rows = sorted((get(r, 'numberofplayers'), get(r, 'side'), get(r, 'hasgoalie'), get(r, 'tacticsidx'),
                   [get(r, f'position{k}') for k in range(13)]) for r in t.records if get(r, 'teamid') == tid)
    bench = [pid[u] for u in roster if u not in (roster[3], roster[1])]
    five = [pid[roster[3]], pid[roster[1]], *bench]
    two = [pid[roster[2]], pid[roster[0]], *(pid[u] for u in roster if u not in (roster[2], roster[0]))]
    pad = lambda order: order + [0] * (13 - len(order))
    assert rows == [(2, 0, 0, 1, pad(two)), (2, 1, 0, 1, pad(two)), (5, 0, 1, 0, pad(five)), (5, 1, 1, 0, pad(five))]

    catalog = fscatalog.Catalog(game)
    team.lineups = [model.Lineup(players=4, goalkeeper=False, tactic=2, starters=['x', roster[0], roster[0]]),
                    model.Lineup(players=4, goalkeeper=False)]
    codes = {i.code for i in validation.validate(project, catalog, PALMEIRAS) if i.entity == team.uid}
    assert {'lineup_tactic_invalid', 'lineup_mode_repeated', 'lineup_player_repeated',
            'lineup_player_not_in_roster'} <= codes


def test_set_piece_takers_default_to_the_captain(game):
    """Each set-piece role can have its own player; a role left out is the captain's."""
    from fsmod import t3db
    project = load_palmeiras()
    team = project.teams[0]
    roster = project.roster(team.uid)
    team.captain = roster[0].uid
    team.takers = {'left_corner': roster[1].uid, 'penalty': roster[2].uid}
    result = builder.build(project, game, PALMEIRAS)
    db = t3db.Database(result.database, game.meta)
    teams = db.by_name('teams')
    get = lambda r, f: teams.value(r, teams.field(f))
    tid = result.assigned_team_ids[team.uid]
    row = next(r for r in teams.records if get(r, 'teamid') == tid)
    pid = {p.uid: result.assigned_player_ids[p.uid] for p in roster}
    assert get(row, 'captainid') == pid[roster[0].uid]
    assert get(row, 'leftcornerkicktakerid') == pid[roster[1].uid]
    assert get(row, 'penaltytakerid') == pid[roster[2].uid]
    assert get(row, 'rightcornerkicktakerid') == get(row, 'freekicktakerid') == pid[roster[0].uid]
