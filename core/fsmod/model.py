"""Project model: the whole mod (new leagues, teams and players).

This is contract v2: separate entity lists with stable app ids
(uid), English keys. Pydantic validates the JSON shape (types, color ranges); game rules (free ids,
ids, roster size, name characters...) live in validation.py.
from_v1() converts the older v1 contract (Portuguese keys, players nested inside teams).
"""
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONTRACT_VERSION = 2
DEFAULT_TEMPLATE_TEAM = 112298  # generic FS4 team whose rows a new team clones (Team.template)

Channel = Annotated[int, Field(ge=0, le=255)]
RGB = tuple[Channel, Channel, Channel]
KitKind = Literal['home', 'away']
KitPart = Literal['jersey', 'shorts', 'socks']
RealKitSlot = Literal['home', 'away', 'goalkeeper']
REAL_KIT_FILES = ('thumbnail', 'jersey', 'shorts')  # image fields of a RealKit
StreetPartName = Literal['top', 'bottom', 'socks']
TakerRole = Literal['penalty', 'free_kick', 'long_free_kick', 'left_corner', 'right_corner']
PlayerRef = Union[str, int]  # project player uid, or playerid of one of the game's own players


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
    shorts_number: Optional[bool] = None  # shortsnumberplacementcode (number on the shorts); None = keep the row's
    # (new team: the template's, off; original team: the game's)

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
    hair_mode: str = 'standard'  # hair converter, a key of scanface.HAIR_MODES (chosen by eye in the preview)
    hair_thickness: float = 0.4  # strand thickness of the 'thick' hair modes (scanface.HAIR_THICKNESS)


TeamKey = Union[str, int]  # new team uid, or teamid of one of the game's teams (edited in the project or not)


class TeamLink(BaseModel):
    """One team of a player (a teamplayerlinks row): each team has its own shirt number and position."""
    team: TeamKey
    number: Optional[int] = None  # None: new team = the template's (original player: his own); game team = a free one
    position: Optional[int] = None  # None: new team = the template's (original player: his own); game team = the
    # player's position in his first team


class OriginalPlayerSnapshot(BaseModel):
    """What the app loaded from the game when the user started editing one of its players (fsmod.original_player):
    the build only rewrites what changed."""
    player: dict = {}  # the editable Player fields as loaded (JSON, original_player.EDITABLE_FIELDS)
    images: dict[str, str] = {}  # SHA-1 of each image as loaded ('photo')


class Player(Entity):
    uid: str
    first_name: str
    last_name: str
    player_id: Optional[int] = None  # playerid in the game (a new one, unused by the game); None = given by the build
    original_id: Optional[int] = None  # the game's own player this entry edits (same playerid); None = new player
    loaded: Optional[OriginalPlayerSnapshot] = None  # original player: what was loaded from the game
    teams: list[TeamLink] = []  # clubs and national teams; none = free agent (kept only in the app)
    generic: bool = True  # generic head (appearance codes); False = scanned face (face; original player without
    # face: the game's own scanned head)
    display_name: Optional[str] = None
    jersey_name: Optional[str] = None
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

    @model_validator(mode='before')
    @classmethod
    def _single_team(cls, data):
        """Projects saved before players had several teams: team + number + position become the first link."""
        if isinstance(data, dict) and 'teams' not in data and {'team', 'number', 'position'} & set(data):
            data = dict(data)
            team, number, position = data.pop('team', None), data.pop('number', None), data.pop('position', None)
            data['teams'] = [{'team': team, 'number': number, 'position': position}] if team is not None else []
        return data

    @property
    def shown_name(self):
        return self.display_name or f'{self.first_name} {self.last_name}'.strip()

    def link(self, team):
        """The TeamLink of team (TeamKey), or None."""
        return next((lk for lk in self.teams if lk.team == team), None)

    @property
    def is_original(self):
        return self.original_id is not None

    @property
    def ref(self):
        """What a lineup, captain or taker names this player by: the uid of a new player, the playerid of an
        original one (the game's players are named by playerid, edited or not)."""
        return self.original_id if self.is_original else self.uid


class Lineup(BaseModel):
    """Starting lineup of one game mode (fs4lineup in data8): it seeds a new save. A mode is
    (players, goalkeeper); a team without a lineup for a mode gets the game's own pick."""
    players: Annotated[int, Field(ge=1, le=6)]  # numberofplayers
    goalkeeper: bool  # hasgoalie
    tactic: int = 1  # fs4tactics id: 0 static, 1 dynamic, 2 street (only 5 and 6 players have 0 and 2)
    starters: list[Optional[PlayerRef]] = []  # player per slot (areas of fs4playersareas); None = filled by the build
    reserves: list[PlayerRef] = []  # bench order; players left out follow in roster order
    # players: Player.ref (new player uids and/or playerids of the game's players)


class OriginalSnapshot(BaseModel):
    """What the app loaded from the game when the user started editing one of its teams (fsmod.original_team): the
    build compares the team with it and only rewrites what changed, so untouched files and rows stay the game's
    own (no DXT re-compression, the street pieces the game picks at random kept)."""
    team: dict = {}  # the editable Team fields as loaded (JSON, original_team.EDITABLE_FIELDS)
    images: dict[str, str] = {}  # SHA-1 of each image as loaded, by field path ('crest', 'real_kits.home.jersey'...)


class Team(Entity):
    uid: str
    name: str
    league: Union[int, str]  # uid of a new league or id of an original league
    primary_color: RGB
    secondary_color: RGB
    team_id: Optional[int] = None  # teamid in the game (a new one, unused by the game); None = given by the build
    original_id: Optional[int] = None  # the game's own team this entry edits (same teamid in the game); None = new
    loaded: Optional[OriginalSnapshot] = None  # original team: what was loaded from the game (fsmod.original_team)
    short_name: Optional[str] = None
    name_10: Optional[str] = None
    name_7: Optional[str] = None
    abbreviation: Optional[str] = None
    crest: Optional[str] = None  # image path relative to the project folder
    kits: dict[KitKind, dict[KitPart, RGB]] = {}  # partial overrides of the default kit colors
    street_kits: dict[KitKind, StreetKit] = {}  # street (FS4) clothes chosen piece by piece
    use_real_kits: bool = False  # team kits from real_kits (FIFA 14-16 packs) instead of solid color + crest
    real_kits: dict[RealKitSlot, RealKit] = {}  # kept when use_real_kits is off (switching back keeps them)
    template: int = DEFAULT_TEMPLATE_TEAM  # generic FS4 team whose rows are cloned (default values: players, street
    # kits)
    captain: Optional[PlayerRef] = None  # Player.ref (new player uid or the game's playerid); None = new team: first
    # player, original team: the game's
    takers: dict[TakerRole, PlayerRef] = {}  # set pieces; a role left out = the captain (original team: the game's)
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

    @property
    def is_original(self):
        return self.original_id is not None

    @property
    def key(self):
        """What a TeamLink names this team by: the uid of a new team, the teamid of an original one."""
        return self.original_id if self.is_original else self.uid


class OriginalChanges(BaseModel):
    """Changes to the game's own leagues, teams and stadiums; only what differs from the game."""
    hidden_leagues: list[int] = []  # leagueids taken out of the league selector (their teams are hidden too)
    hidden_teams: list[int] = []  # teamids taken out of their league
    team_locks: dict[int, bool] = {}  # teamid -> locked; only teams the game can lock (catalog.lockable_team_ids)
    stadium_locks: dict[int, bool] = {}  # stadiumid -> locked; only lockable stadiums (catalog.stadiums)


class GamePatches(BaseModel):
    """Optional changes to the game's own scripts (fsmod.gamepatches); all off by default."""
    close_up_heads: bool = False  # players keep the close-up head, hair and eyes at any camera distance


class Project(Entity):
    version: Literal[2] = CONTRACT_VERSION
    leagues: list[League] = []
    teams: list[Team] = []
    players: list[Player] = []
    originals: OriginalChanges = OriginalChanges()
    game_patches: GamePatches = GamePatches()

    @property
    def new_players(self):
        return [p for p in self.players if not p.is_original]

    @property
    def original_players(self):
        """Entries that edit the game's own players (Player.original_id)."""
        return [p for p in self.players if p.is_original]

    def roster(self, team):
        """The project's players of a team (TeamKey: new team uid or the game's teamid), in project order."""
        return [p for p in self.players if p.link(team)]

    @property
    def new_teams(self):
        return [t for t in self.teams if not t.is_original]

    @property
    def original_teams(self):
        """Entries that edit the game's own teams (Team.original_id)."""
        return [t for t in self.teams if t.is_original]

    def visible(self):
        """The project without what the user hid: hidden leagues (and their teams), hidden teams (and their
        players) and hidden players. This is what goes into the patch and what is validated."""
        leagues = [lg for lg in self.leagues if not lg.hidden]
        hidden_leagues = {lg.uid for lg in self.leagues if lg.hidden}
        teams = [t for t in self.teams if not t.hidden and t.league not in hidden_leagues]
        left_out = {t.uid for t in self.teams if not t.is_original} - {t.uid for t in teams}
        players = []
        for p in self.players:
            links = [lk for lk in p.teams if lk.team not in left_out]
            if p.hidden or (p.teams and not links):  # every team of the player is hidden
                continue
            players.append(p if len(links) == len(p.teams) else p.model_copy(update={'teams': links}))
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
                uid=puid, teams=[TeamLink(team=uid, number=j.get('numero'), position=j.get('posicao'))],
                first_name=j['nome'], last_name=j['sobrenome'],
                display_name=j.get('exibido'), jersey_name=j.get('camisa_nome'), template=j.get('molde'),
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
