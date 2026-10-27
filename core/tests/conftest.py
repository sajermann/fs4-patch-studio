import os
import sys

import pytest

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(CORE))
sys.path.insert(0, CORE)

from fsmod.game import default_sources  # noqa: E402

FIXTURES = os.path.join(CORE, 'tests', 'fixtures')
# Palmeiras build validated in game (19/10/2026); game-derived, so it lives outside git
REFERENCE = os.path.join(REPO, 'pesquisa', 'referencia', 'palmeiras_validado')


@pytest.fixture(scope='session')
def game():
    sources = default_sources()
    missing = sources.missing_files()
    if missing:
        pytest.skip(f'original game files not available in {sources.folder}: {missing}')
    return sources
