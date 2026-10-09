import json
import re
from importlib.resources import files
from pathlib import Path

from .domain import RankingError


def load_confindustria_members(source: Path | None = None) -> frozenset[str]:
    resource = (
        source
        if source is not None
        else files("warera_rankings").joinpath("data/confindustria.json")
    )
    try:
        members = json.loads(resource.read_text(encoding="utf-8"))
        if not isinstance(members, list) or any(
            not isinstance(player_id, str) or not re.fullmatch(r"[a-f\d]{24}", player_id)
            for player_id in members
        ):
            raise ValueError
    except ValueError as error:
        raise RankingError(
            "Lista membri Confindustria non valida: usare un array di ID WarEra"
        ) from error
    return frozenset(members)
