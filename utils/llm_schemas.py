"""Pydantic contracts for all structured LLM responses."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlannerResponse(_StrictSchema):
    action: Literal["write", "update"]
    instruction: str

    @field_validator("instruction")
    @classmethod
    def instruction_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("instruction must not be blank")
        return value


class RatingScores(_StrictSchema):
    layout: int = Field(ge=0, le=10)
    typography: int = Field(ge=0, le=10)
    responsiveness: int = Field(ge=0, le=10)
    visual_design: int = Field(ge=0, le=10)
    description_match: int = Field(ge=0, le=10)


class RaterResponse(_StrictSchema):
    scores: RatingScores
    deductions: str


class CriteriaUpdaterResponse(_StrictSchema):
    updated_criteria: str
    changelog: str
