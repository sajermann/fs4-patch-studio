"""Command line: python -m fsmod build <project.json> [out_dir]   (default out_dir: app/backend/patch)

Accepts contract v1 projects. Slots chosen during the build are written back
into the JSON so they stay stable.
"""
import json
import os
import sys

from . import builder, model
from .game import MissingOriginalFiles, default_patch_dir, default_sources


def main(argv):
    if len(argv) < 2 or argv[0] != 'build':
        sys.exit(__doc__)
    path = argv[1]
    out_dir = argv[2] if len(argv) > 2 else default_patch_dir()
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    project = model.from_v1(data)
    game = default_sources()
    try:
        result = builder.build(project, game, os.path.dirname(os.path.abspath(path)), log=print)
    except (builder.BuildError, MissingOriginalFiles) as e:
        sys.exit(f'ERROR: {e}')
    for uid, lid in result.assigned_league_ids.items():
        print(f'league {uid} -> leagueid {lid}')
    for uid, tid in result.assigned_team_ids.items():
        print(f'team {uid} -> teamid {tid}')
    for uid, pid in result.assigned_player_ids.items():
        print(f'player {uid} -> playerid {pid}')
    print('->', builder.write_patch(result, game, out_dir))


if __name__ == '__main__':
    main(sys.argv[1:])
