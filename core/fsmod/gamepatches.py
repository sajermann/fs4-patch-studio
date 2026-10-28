"""Optional changes to the game's own scripts ("game patches"), switched on per project (Project.game_patches).

The game reads its Lua scripts only from data0.big: unlike the database, an entry in data8.big does not replace them
(validated in game). So a patch here replaces the script entry inside data0, which then goes whole into the patch.

close_up_heads: data/fifarna/lua/assets/player.lua binds 4 levels of detail (LOD) per player: 0 = close-up
(PlayerAssetHighLod: scanned head, hair, eyes), 1 and 2 = far (PlayerAssetLowLod: a generic low-detail head whose
texture layout does not match FIFA 14-16 face textures, so real faces change a lot from afar and some show the teeth
on the ear), 3 = shadow. The patch makes LOD 1 and 2 use PlayerAssetHighLod too: every player is drawn with the
close-up assets at any distance (validated in game).
"""
from . import chunk

PLAYER_LUA = 'data/fifarna/lua/assets/player.lua'
LOW_LOD_BRANCH = (b'\telseif (lod == 1) then\r\n\t\tPlayerAssetLowLod(player, lod)\t\r\n'
                  b'\telseif (lod == 2) then\r\n\t\tPlayerAssetLowLod(player, lod)\t\r\n')
HIGH_LOD_BRANCH = LOW_LOD_BRANCH.replace(b'PlayerAssetLowLod', b'PlayerAssetHighLod')


class GamePatchError(ValueError):
    pass


def close_up_heads(game):
    """{('data0.big', player.lua): chunkzip of the script with LOD 1 and 2 bound to the close-up assets}."""
    lua = chunk.decode(game.read_entry(PLAYER_LUA)[2])
    if lua.count(LOW_LOD_BRANCH) != 1:
        raise GamePatchError(f'{PLAYER_LUA}: LOD branch not found')
    return {('data0.big', PLAYER_LUA): chunk.chunkzip(lua.replace(LOW_LOD_BRANCH, HIGH_LOD_BRANCH))}


# field of model.GamePatches -> function(game) giving the replaced archive entries
PATCHES = {'close_up_heads': close_up_heads}


def entries(game, patches):
    """Replaced archive entries of the game patches switched on in patches (model.GamePatches)."""
    out = {}
    for name, build in PATCHES.items():
        if getattr(patches, name):
            out.update(build(game))
    return out
