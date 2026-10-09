import pytest

from warera_rankings.domain import RankingError
from warera_rankings.memberships import load_confindustria_members


def test_initial_confindustria_members():
    assert load_confindustria_members() == {
        "69e60890fe61f8ad03b860ba",
        "69d4dd1c70ab5601d0eb54d9",
    }


@pytest.mark.parametrize("content", ['{"members": []}', '["Giancarlo_Devasini"]', "[42]", "{"])
def test_invalid_membership_file_fails_explicitly(tmp_path, content):
    source = tmp_path / "members.json"
    source.write_text(content)
    with pytest.raises(RankingError, match="Confindustria"):
        load_confindustria_members(source)
