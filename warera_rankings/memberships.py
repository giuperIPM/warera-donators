import re

import httpx

from .domain import RankingError

MEMBERS_URL = "https://confindustria-rust.vercel.app/players.json"


async def load_confindustria_members(http: httpx.AsyncClient) -> frozenset[str]:
    try:
        response = await http.get(MEMBERS_URL)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise RankingError("Lista membri Confindustria non raggiungibile") from error
    try:
        members = response.json()
        if not isinstance(members, list) or any(
            not isinstance(member, dict)
            or not isinstance(member.get("id"), str)
            or not re.fullmatch(r"[a-f\d]{24}", member["id"])
            for member in members
        ):
            raise ValueError
    except ValueError as error:
        raise RankingError(
            "Lista membri Confindustria non valida: ID WarEra mancanti o invalidi"
        ) from error
    return frozenset(member["id"] for member in members)
