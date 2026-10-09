import tomllib
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .domain import RankingError


class QuitConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    minimum_signals: int = Field(default=4, ge=4, le=7)
    max_weekly_works: int = Field(default=5, ge=0)
    max_weekly_missions: int = Field(default=5, ge=0)
    inactive_days: int = Field(default=3, ge=1)
    max_money: Decimal = Field(default=Decimal("10"), ge=0, allow_inf_nan=False)
    max_equipment_value: Decimal = Field(default=Decimal("100"), ge=0, allow_inf_nan=False)
    max_company_value: Decimal = Field(default=Decimal("1000"), ge=0, allow_inf_nan=False)
    concentration_minutes: int = Field(default=10, ge=1)
    concentration_share: Decimal = Field(default=Decimal("0.8"), gt=0, le=1)


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quit_detection: QuitConfig = Field(default_factory=QuitConfig)


def load_config(path: Path) -> QuitConfig:
    try:
        with path.open("rb") as file:
            return Config.model_validate(tomllib.load(file)).quit_detection
    except (tomllib.TOMLDecodeError, ValidationError) as error:
        raise RankingError(f"Configurazione non valida: {path}") from error
