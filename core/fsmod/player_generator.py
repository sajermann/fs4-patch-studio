"""Fills the free places of a new team with placeholder players: strikers with every skill at the middle of its range,
named Player 01, Player 02... (skipping the names the team already has) and random in everything else (generic head
included)."""
import datetime
import itertools
import os
import random

from . import body, builder
from .catalog import SKILLS
from .model import Player, TeamLink

STRIKER_POSITION = 25
NUMBERS = range(1, 100)  # what the roster screen accepts
HEIGHTS = (165, 195)
WEIGHTS = (60, 90)
BIRTHDATES = (datetime.date(1980, 1, 1), datetime.date(1994, 12, 31))


def _taken_numbers(project, team, catalog):
    """Shirt numbers in use in a new team: the ones set in the project and the ones inherited from the template."""
    defaults = catalog.player_defaults(project)
    taken = set()
    for player in project.roster(team):
        number = player.link(team).number
        if number is None:
            inherited = defaults.get(player.uid, {})
            number = inherited.get('number') if inherited.get('team') == team else None
        taken.add(number)
    return taken


def _appearance(catalog, height, rng):
    look = {code: rng.choice(values) for code, values in catalog.generic_appearance_options.items() if values}
    look['bodytypecode'] = rng.choice(body.codes(height))
    return look


def generate(project, team, catalog, rng=random):
    """The new Players that complete the roster of a new team (uid), up to builder.MAX_ROSTER. Hidden players stay
    out of the patch, so they do not take a place."""
    count = builder.MAX_ROSTER - sum(not p.hidden for p in project.roster(team))
    numbers = rng.sample([n for n in NUMBERS if n not in _taken_numbers(project, team, catalog)], max(count, 0))
    names = {p.shown_name for p in project.roster(team)}
    indexes = (i for i in itertools.count(1) if f'Player {i:02d}' not in names)
    nations = [nation['id'] for nation in catalog.nations]
    first_day, last_day = (day.toordinal() for day in BIRTHDATES)
    skills = {skill: (low + high) // 2 for skill, (low, high) in SKILLS.items()}
    heights = [rng.randint(*HEIGHTS) for _ in numbers]
    return [Player(
        uid='u' + os.urandom(6).hex(),  # starts with a letter: an all-digit address names a game id
        first_name='Player',
        last_name=f'{index:02d}',
        jersey_name=f'Player {index:02d}',  # the back of the shirt would otherwise show only the last name
        teams=[TeamLink(team=team, number=number, position=STRIKER_POSITION)],
        generic=True,
        height=height,
        weight=rng.randint(*WEIGHTS),
        birthdate=datetime.date.fromordinal(rng.randint(first_day, last_day)).isoformat(),
        foot=rng.choice(('right', 'left')),
        skills=skills,
        appearance=_appearance(catalog, height, rng),
        fields={'nationality': rng.choice(nations)},
    ) for number, height, index in zip(numbers, heights, indexes)]
