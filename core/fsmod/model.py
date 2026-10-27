"""Project model: the whole mod (new leagues, teams and players).

This is contract v2: separate entity lists with stable app ids
(uid), English keys. Pydantic validates the JSON shape (types, color ranges); game rules (free ids,
ids, roster size, name characters...) live in validation.py.
from_v1() converts the older v1 contract (Portuguese keys, players nested inside teams).
"""
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = 2

Channel = Annotated[int, Field(ge=0, le=255)]
RGB = tuple[Channel, Channel, Channel]
KitKind = Literal['home', 'away']
KitPart = Literal['jersey', 'shorts', 'socks']
RealKitSlot = Literal['home', 'away', 'goalkeeper']
REAL_KIT_FILES = ('thumbnail', 'jersey', 'shorts')  # image fields of a RealKit
StreetPartName = Literal['top', 'bottom', 'socks']


class Entity(BaseModel):
    model_config = ConfigDict(extra='ignore')


class League(Entity):
    uid: str
    name: str
    league_id: Optional[int] = None  # leagueid in the game (a new one, unused by the game); None = given by the build
    short_name: Optional[str] = None
    internal_name: Optional[str] = None
    sort_order: int = 6
    image: Optional[str] = None  # league image in the selector (fsmod.leaguelogo); project folder path
    wide_image: Optional[str] = None  # wide flag (shown once the league is chosen); None = image
    wide_image_fit: Literal['contain', 'cover'] = 'contain'  # whole image / fill the wide area (cropped)
    hidden: bool = False  # left out of the patch (with its teams), e.g. not ready yet


class StreetPart(BaseModel):
    """One piece of a street kit (teamkits): mesh type, texture variation and the 3 colors painted on its mask
    (red = primary, green = secondary, blue = tertiary)."""
    style: int  # top/bottom/sock_geo_type
    pattern: int  # *_texture_pattern (variation of clothes/<part>_<style>_<pattern>_cm.rx3)
    colors: tuple[RGB, RGB, RGB]


class StreetKit(BaseModel):
    """Street Home/Away (teamkits kittype 0/1). A missing part keeps the template's pieces (the game picks one
    of them at random) with colors derived from the team kit."""
    top: Optional[StreetPart] = None
    bottom: Optional[StreetPart] = None
    socks: Optional[StreetPart] = None


class KitColors(BaseModel):
    jersey: RGB
    shorts: RGB
    socks: RGB


class RealKit(BaseModel):
    """Real kit of a FIFA 14-16 pack (fsmod.kit.build_real) for one slot: PNGs in the project folder + the teamkits
    fields the pack's author tells (or the user picks). A slot without jersey or shorts is not used."""
    thumbnail: Optional[str] = None  # kit-screen thumbnail (256x256); None = generic one tinted with the jersey
    jersey: Optional[str] = None  # 2048x2048 (any square size)
    shorts: Optional[str] = None  # 2048x1024 (any 2:1 size)
    name_color: RGB = (255, 255, 255)  # jerseynamecolorr/g/b
    number_color: int = 1  # numbercolor: palette index (fsmod.kit.NUMBER_COLORS; 1 white, 2 black...)
    shorts_number_color: int = 1  # shortsnumbercolor
    collar: int = 0  # jerseycollargeometrytype ("collar N" in the packs)
    front_number: bool = False  # jerseyfrontnumberplacementcode (the packs bring the front without room for it)

    @property
    def complete(self):
        return bool(self.jersey and self.shorts)


class ScannedFace(BaseModel):
    """Real face from a FIFA 14 pack (fsmod.scanface): the pack's files of that face are copied into the project
    folder (scanface.PROJECT_DIR/<player uid>/, pack names) when the user picks it; the build converts them."""
    source_id: int  # id of the face in the pack (its file names)
    pack: Optional[str] = None  # pack folder it came from, for reference only
    paint_scalp: bool = True  # paint the hair color on the scalp (scanface.paint_scalp); off for faces whose texture
    # already brings the hair painted and whose cap hangs over the forehead (Yamal: dark streaks)


class Player(Entity):
    uid: str
    first_name: str
    last_name: str
    player_id: Optional[int] = None  # playerid in the game (a new one, unused by the game); None = given by the build
    team: Optional[str] = None  # team uid; None = free agent (kept only in the app)
    generic: bool = True  # generic head (appearance codes); False = scanned face (face)
    display_name: Optional[str] = None
    jersey_name: Optional[str] = None
    number: Optional[int] = None
    position: Optional[int] = None
    template: Optional[int] = None  # playerid whose record is cloned
    height: Optional[int] = None
    weight: Optional[int] = None
    birthdate: Optional[str] = None  # YYYY-MM-DD
    foot: Optional[Literal['right', 'left']] = None
    skills: dict[str, int] = {}  # ATH DEF DRI GK PAS SHO SPE (1-99), TRI (0-4), overall
    appearance: dict[str, int] = {}  # generic head codes: headtypecode, hairtypecode, haircolorcode...
    fields: dict[str, int] = {}  # any other column of the players table (advanced)
    photo: Optional[str] = None  # menu photo, image path relative to the project folder
    face: Optional[ScannedFace] = None  # used when generic is False
    hidden: bool = False  # left out of the patch (its id stays reserved), e.g. not ready yet

    @property
    def shown_name(self):
        return self.display_name or f'{self.first_name} {self.last_name}'.strip()


class Lineup(BaseModel):
    """Starting lineup of one game mode (fs4lineup in data8): it seeds a new save. A mode is
    (players, goalkeeper); a team without a lineup for a mode gets the game's own pick."""
    players: Annotated[int, Field(ge=1, le=6)]  # numberofplayers
    goalkeeper: bool  # hasgoalie
    tactic: int = 1  # fs4tactics id: 0 static, 1 dynamic, 2 street (only 5 and 6 players have 0 and 2)
    starters: list[Optional[str]] = []  # player uid per slot (areas of fs4playersareas); None = filled by the build
    reserves: list[str] = []  # bench order; players left out follow in roster order


class Team(Entity):
    uid: str
    name: str
    league: Union[int, str]  # uid of a new league or id of an original league
    primary_color: RGB
    secondary_color: RGB
    team_id: Optional[int] = None  # teamid in the game (a new one, unused by the game); None = given by the build
    short_name: Optional[str] = None
    name_10: Optional[str] = None
    name_7: Optional[str] = None
    abbreviation: Optional[str] = None
    crest: Optional[str] = None  # image path relative to the project folder
    kits: dict[KitKind, dict[KitPart, RGB]] = {}  # partial overrides of the default kit colors
    street_kits: dict[KitKind, StreetKit] = {}  # street (FS4) clothes chosen piece by piece
    use_real_kits: bool = False  # team kits from real_kits (FIFA 14-16 packs) instead of solid color + crest
    real_kits: dict[RealKitSlot, RealKit] = {}  # kept when use_real_kits is off (switching back keeps them)
    template: int = 112298  # generic FS4 team whose rows are cloned (default values: players, street kits)
    captain: Optional[str] = None  # player uid; None = first player
    lineups: list[Lineup] = []  # starting lineup per game mode (fs4lineup); a mode without one = the game's pick
    hidden: bool = False  # left out of the patch (with its players), e.g. not ready yet

    def kit(self, kind):
        """Full KitColors for 'home' / 'away' (defaults derived from the team colors)."""
        p, s = tuple(self.primary_color), tuple(self.secondary_color)
        base = {'jersey': p, 'shorts': s, 'socks': p} if kind == 'home' else {'jersey': s, 'shorts': p, 'socks': s}
        base.update({k: tuple(v) for k, v in self.kits.get(kind, {}).items()})
        return KitColors(**base)

    def real_kit(self, slot):
        """The RealKit the build uses for slot, or None (generic kit; goalkeeper: the game's default)."""
        k = self.real_kits.get(slot) if self.use_real_kits else None
        return k if k and k.complete else None


class OriginalChanges(BaseModel):
    """Changes to the game's own leagues, teams and stadiums; only what differs from the game."""
    hidden_leagues: list[int] = []  # leagueids taken out of the league selector (their teams are hidden too)
    hidden_teams: list[int] = []  # teamids taken out of their league
    team_locks: dict[int, bool] = {}  # teamid -> locked; only teams the game can lock (catalog.lockable_team_ids)
    stadium_locks: dict[int, bool] = {}  # stadiumid -> locked; only lockable stadiums (catalog.stadiums)


class Project(Entity):
    version: Literal[2] = CONTRACT_VERSION
    leagues: list[League] = []
    teams: list[Team] = []
    players: list[Player] = []
    originals: OriginalChanges = OriginalChanges()

    def roster(self, team_uid):
        return [p for p in self.players if p.team == team_uid]

    def visible(self):
        """The project without what the user hid: hidden leagues (and their teams), hidden teams (and their
        players) and hidden players. This is what goes into the patch and what is validated."""
        leagues = [lg for lg in self.leagues if not lg.hidden]
        hidden_leagues = {lg.uid for lg in self.leagues if lg.hidden}
        teams = [t for t in self.teams if not t.hidden and t.league not in hidden_leagues]
        kept = {t.uid for t in teams}
        players = [p for p in self.players if not p.hidden and (p.team is None or p.team in kept)]
        return self.model_copy(update={'leagues': leagues, 'teams': teams, 'players': players})

    def to_json(self):
        return self.model_dump(mode='json', exclude_none=True)


def load(data):
    """Project from a v1 or v2 dict."""
    if data.get('versao') == 1:
        return from_v1(data)
    return Project.model_validate(data)


# ---------------------------------------------------------------- contract v1
V1_KIT_PARTS = {'camisa': 'jersey', 'calcao': 'shorts', 'meiao': 'socks'}


def from_v1(data):
    """Project from a v1 dict."""
    if data.get('versao') != 1:
        raise ValueError('v1 project expected ("versao": 1)')
    leagues, teams, players = [], [], []
    league_uids = {}
    for i, lg in enumerate(data.get('ligas', []), 1):
        uid = f'lg_{i:02d}'
        league_uids[int(lg['id'])] = uid
        leagues.append(League(
            uid=uid, name=lg['nome'], short_name=lg.get('nome_curto'),
            internal_name=lg.get('nome_interno'), sort_order=lg.get('ordem', 6)))
    player_n = 0
    for i, tm in enumerate(data.get('times', []), 1):
        uid = f'tm_{i:02d}'
        player_uids = []
        for j in tm.get('jogadores', []):
            player_n += 1
            puid = f'jg_{player_n:02d}'
            player_uids.append(puid)
            players.append(Player(
                uid=puid, team=uid, first_name=j['nome'], last_name=j['sobrenome'],
                display_name=j.get('exibido'), jersey_name=j.get('camisa_nome'),
                number=j.get('numero'), position=j.get('posicao'), template=j.get('molde'),
                height=j.get('altura'), weight=j.get('peso'), birthdate=j.get('nascimento'),
                foot={'canhoto': 'left', 'destro': 'right'}.get(j.get('pe')),
                skills=dict(j.get('habilidades', {})), fields=dict(j.get('campos', {}))))
        league = int(tm['liga'])
        kits = {kind: {V1_KIT_PARTS[k]: tuple(v) for k, v in parts.items()}
                for kind, parts in tm.get('uniformes', {}).items()}
        captain = int(tm.get('capitao', 0))
        teams.append(Team(
            uid=uid, name=tm['nome'], league=league_uids.get(league, league),
            primary_color=tuple(tm['cor_principal']), secondary_color=tuple(tm['cor_secundaria']),
            short_name=tm.get('nome_curto'), name_10=tm.get('nome_10'),
            name_7=tm.get('nome_7'), abbreviation=tm.get('sigla'), crest=tm.get('escudo'), kits=kits,
            template=int(tm.get('molde', 112298)),
            captain=player_uids[captain] if captain < len(player_uids) else None))
    return Project(leagues=leagues, teams=teams, players=players)
