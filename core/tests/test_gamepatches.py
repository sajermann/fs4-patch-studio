import pytest

from fsmod import builder, chunk, gamepatches, model


def test_game_patches_are_off_by_default(game):
    project = model.load({'version': 2})
    assert project.game_patches == model.GamePatches()
    assert gamepatches.entries(game, project.game_patches) == {}
    assert set(gamepatches.PATCHES) == set(model.GamePatches.model_fields)


def test_close_up_heads_binds_far_lods_to_the_close_up_assets(game):
    out = gamepatches.entries(game, model.GamePatches(close_up_heads=True))
    assert list(out) == [('data0.big', gamepatches.PLAYER_LUA)]
    lua = chunk.decode(out['data0.big', gamepatches.PLAYER_LUA])
    original = chunk.decode(game.read_entry(gamepatches.PLAYER_LUA)[2])
    assert gamepatches.HIGH_LOD_BRANCH in lua and gamepatches.LOW_LOD_BRANCH not in lua
    assert lua == original.replace(gamepatches.LOW_LOD_BRANCH, gamepatches.HIGH_LOD_BRANCH)
    assert b'(lod == 0) then\r\n\t\tPlayerAssetHighLod' in lua and b'PlayerAssetShadow(player, lod)' in lua


def test_build_adds_the_switched_on_game_patches(game, tmp_path):
    project = model.load({'version': 2, 'game_patches': {'close_up_heads': True}})
    result = builder.build(project, game, str(tmp_path))
    assert ('data0.big', gamepatches.PLAYER_LUA) in result.entries
    assert ('data0.big', gamepatches.PLAYER_LUA) not in builder.build(model.load({'version': 2}), game,
                                                                       str(tmp_path)).entries


def test_close_up_heads_fails_clearly_when_the_script_changed(game, monkeypatch):
    monkeypatch.setattr(gamepatches, 'LOW_LOD_BRANCH', b'not in the script')
    with pytest.raises(gamepatches.GamePatchError):
        gamepatches.close_up_heads(game)
