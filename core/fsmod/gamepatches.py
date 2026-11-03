"""Optional changes to the game's own scripts ("game patches"), switched on per project (Project.game_patches).

The game reads its Lua scripts only from data0.big: unlike the database, an entry in data8.big does not replace them
(validated in game). So a patch here replaces the script entry inside data0, which then goes whole into the patch.

close_up_heads: data/fifarna/lua/assets/player.lua binds 4 levels of detail (LOD) per player: 0 = close-up
(PlayerAssetHighLod: scanned head, hair, eyes), 1 and 2 = far (PlayerAssetLowLod: a generic low-detail head whose
texture layout does not match FIFA 14-16 face textures, so real faces change a lot from afar and some show the teeth
on the ear), 3 = shadow. The patch makes LOD 1 and 2 use PlayerAssetHighLod too: every player is drawn with the
close-up assets at any distance (validated in game).

The World Tour friendly match (fsmod.world_tour) also changes the game's scripts, whenever players are picked for it, so
it has no switch of its own:
  - data/ui/game/screens/worldtour/selectlocation.big clears both friendly teams when the country is chosen, which would
    take the picked players out. The name of the call is changed, keeping its length: the screen's script then calls a
    function that does not exist, and nothing happens.
  - player.lua gives every created player the create-player head, whatever his head class. A clone is a created player
    with head class 0 (scanned head), so it goes on as a normal player when choosing assets. Players the game creates
    have head class 2 and do not change.
"""
from . import chunk, leaguelogo

PLAYER_LUA = 'data/fifarna/lua/assets/player.lua'
LOW_LOD_BRANCH = (b'\telseif (lod == 1) then\r\n\t\tPlayerAssetLowLod(player, lod)\t\r\n'
                  b'\telseif (lod == 2) then\r\n\t\tPlayerAssetLowLod(player, lod)\t\r\n')
HIGH_LOD_BRANCH = LOW_LOD_BRANCH.replace(b'PlayerAssetLowLod', b'PlayerAssetHighLod')
SELECT_LOCATION = 'data/ui/game/screens/worldtour/selectlocation.big'
APT_CONSTANTS = '1'  # entry of the Apt archive with the names its script uses
CLEAR_TEAMS_CALL = b'ClearFriendlyMatchTeams'
CLEAR_TEAMS_OFF = b'ClearFriendlyMatchTeamZ'
CREATE_PLAYER_LINE = b'\tdb.player[idx].isCreatePlayer = as:GetInt(player, "isCreatePlayer")\r\n'
SCANNED_HEAD_LINES = (b'\tif (db.player[idx].isCreatePlayer == 1 and db.player[idx].headClass == 0 '
                      b'and db.player[idx].isVirtualPro == 0) then\r\n'
                      b'\t\tdb.player[idx].isCreatePlayer = 0\r\n\tend\r\n')


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


def _refpack_literals(raw):
    """RefPack stream of literal runs only (no compression; the Apt entries are RefPack)."""
    out = bytearray(b'\x10\xfb' + len(raw).to_bytes(3, 'big'))
    pos = 0
    while len(raw) - pos >= 4:
        run = min((len(raw) - pos) // 4 * 4, 112)
        out.append(0xE0 + (run - 4) // 4)
        out += raw[pos:pos + run]
        pos += run
    out.append(0xFC + len(raw) - pos)
    out += raw[pos:]
    return bytes(out)


def _keep_friendly_teams(game):
    """{('data1.big', SELECT_LOCATION): the screen without its call that clears the friendly teams}."""
    archive, tail = leaguelogo.read_bigf(chunk.decode(game.read_entry(SELECT_LOCATION)[2]))
    patched = []
    for name, data in archive:
        if name == APT_CONSTANTS:
            constants = leaguelogo.refpack_decode(data)
            if constants.count(CLEAR_TEAMS_CALL) != 1:
                raise GamePatchError(f'{SELECT_LOCATION}: {CLEAR_TEAMS_CALL.decode()} not found')
            data = _refpack_literals(constants.replace(CLEAR_TEAMS_CALL, CLEAR_TEAMS_OFF))
        patched.append((name, data))
    return {('data1.big', SELECT_LOCATION): chunk.chunkzip(leaguelogo.write_bigf(patched, tail))}


def _scanned_clones(game, out):
    """{('data0.big', player.lua): the script as out leaves it, keeping the scanned head of a clone}."""
    key = ('data0.big', PLAYER_LUA)
    lua = chunk.decode(out[key] if key in out else game.read_entry(PLAYER_LUA)[2])
    if lua.count(CREATE_PLAYER_LINE) != 1:
        raise GamePatchError(f'{PLAYER_LUA}: isCreatePlayer line not found')
    return {key: chunk.chunkzip(lua.replace(CREATE_PLAYER_LINE, CREATE_PLAYER_LINE + SCANNED_HEAD_LINES))}


def entries(game, patches, world_tour=None):
    """Replaced archive entries of the game patches switched on in patches (model.GamePatches) and of the players picked
    for the World Tour friendly match (model.WorldTour)."""
    out = {}
    for name, build in PATCHES.items():
        if getattr(patches, name):
            out.update(build(game))
    if world_tour and world_tour.slots:
        out.update(_keep_friendly_teams(game))
        if world_tour.has_clones:
            out.update(_scanned_clones(game, out))
    return out
