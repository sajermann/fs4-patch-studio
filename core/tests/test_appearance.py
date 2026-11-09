import random

from fsmod import appearance_thumbs, body, builder, catalog, player_generator, preview
from fsmod import model
from fsmod.model import Project, Team


def test_options_have_what_the_game_offers_beyond_generic_players(game):
    c = catalog.Catalog(game)
    assert c.appearance_options['haircolorcode'] == list(range(12))
    assert set(c.generic_appearance_options['haircolorcode']) == {0, 1, 2, 3, 4, 5, 6, 7, 9}
    hairs = c.appearance_options['hairtypecode']
    assert set(c.generic_appearance_options['hairtypecode']) < set(hairs)
    assert {7, 50, 91} <= set(hairs)
    assert all(game.locate(f'data/sceneassets/hair/hair_{h}_1_0.rx3') for h in hairs if h)
    assert all(preview.hair_color(code) != '#ff0000' for code in c.appearance_options['haircolorcode'])


def test_every_option_fits_the_players_table(game):
    c = catalog.Catalog(game)
    players = c.db.table('players')
    row = [None] * len(players.fields)
    for field, options in c.appearance_options.items():
        for option in options:
            builder.Db.put(players, row, field, option)  # raises BuildError when the field cannot hold it


def test_hair_groups_cover_every_hair_once(game):
    c = catalog.Catalog(game)
    groups = {g['key']: g['codes'] for g in c.hair_groups}
    assert sorted(code for codes in groups.values() for code in codes) == c.appearance_options['hairtypecode']
    assert list(groups) == ['afro', 'very_short', 'short', 'medium', 'long', 'helmets', 'other']
    assert groups['other'] == [27]
    assert groups['helmets'] == [50]
    assert 0 in groups['very_short']  # bald


def test_body_type_follows_the_height():
    assert body.codes(170) == (7, 8, 9)
    assert body.codes(171) == (1, 2, 3)
    assert body.codes(184) == (1, 2, 3)
    assert body.codes(185) == (4, 5, 6)


def test_the_build_is_kept_when_the_height_class_changes():
    assert [body.fit(code, 190) for code in range(1, 10)] == [4, 5, 6] * 3
    assert [body.fit(code, 165) for code in range(1, 10)] == [7, 8, 9] * 3
    assert body.fit(6, 178) == 3  # tall stocky at 178 cm: normal stocky


def test_the_build_writes_the_body_type_of_the_player_s_height(game, tmp_path):
    players = [{'uid': 'tall', 'first_name': 'A', 'last_name': 'Tall', 'height': 192, 'appearance': {'bodytypecode': 3}},
               {'uid': 'short', 'first_name': 'B', 'last_name': 'Short', 'height': 166, 'appearance': {'bodytypecode': 1}},
               {'uid': 'normal', 'first_name': 'C', 'last_name': 'Normal', 'height': 178, 'appearance': {'bodytypecode': 5}}]
    data = {'version': model.CONTRACT_VERSION, 'players': players,
            'world_tour': {'white': [{'player': p['uid'], 'mode': 'original'} for p in players]}}
    result = builder.build(model.load(data), game, str(tmp_path))
    db = builder.Db(result.database, game.meta)
    table = db.table('players')
    shown = {uid: db.get(table, table.records[db.rows('players', 'playerid', pid)[0]], 'bodytypecode')
             for uid, pid in result.assigned_player_ids.items()}
    assert shown == {'tall': 6, 'short': 7, 'normal': 2}  # same build, the class of the height


def test_generated_players_are_coherent_and_keep_natural_looks(game):
    c = catalog.Catalog(game)
    project = Project(teams=[Team(uid='t1', name='T', leagues=[], primary_color=(0, 0, 0), secondary_color=(255, 255, 255))])
    generated = player_generator.generate(project, 't1', c, random.Random(1))
    assert generated
    natural = c.generic_appearance_options
    for player in generated:
        assert player.appearance['bodytypecode'] in body.codes(player.height)
        assert player.appearance['haircolorcode'] in natural['haircolorcode']
        assert player.appearance['hairtypecode'] in natural['hairtypecode']


def test_thumbnails_are_square_around_the_subject(game):
    for field, code, variant in (('hairtypecode', 100, 8), ('hairtypecode', 0, 1), ('haircolorcode', 11, 0),
                                 ('facialhairtypecode', 4, 2), ('facialhaircolorcode', 4, 0), ('eyecolorcode', 7, 0),
                                 ('eyecolorcode', 1, 0), ('eyebrowcode', 2, 0)):
        image = appearance_thumbs.thumbnail(game, field, code, variant)
        assert image.size == (128, 128), field
        assert image.mode == 'RGBA'
        assert image.getchannel('A').getbbox()[3] == 128, field  # the picture reaches the bottom: nothing empty below it


def test_codes_without_a_thumbnail(game):
    assert appearance_thumbs.thumbnail(game, 'hairtypecode', 27, 1) is None
    assert appearance_thumbs.thumbnail(game, 'eyecolorcode', 0) is None
