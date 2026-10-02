"""Validated HTTP contracts; limits bound both provider cost and database size."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Credentials(InputModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("email")
    @classmethod
    def email_address(cls, value):
        import re
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address.")
        return value.lower()


class Registration(Credentials):
    name: str = Field(min_length=2, max_length=60)


class ProjectInput(InputModel):
    title: str = Field(min_length=2, max_length=100)
    description: str = Field(min_length=20, max_length=3000)


class RunInput(InputModel):
    mode: Literal["live", "demo"] = "live"
    profile_id: str = Field(min_length=1, max_length=64)
    max_iterations: int = Field(default=4, ge=3, le=6)


class ProfileInput(InputModel):
    name: str = Field(min_length=1, max_length=48)
    criteria: str = Field(min_length=1, max_length=4000)


class ProfileEdit(InputModel):
    criteria: str = Field(min_length=1, max_length=4000)
    changelog: str = Field(default="Updated criteria.", min_length=1, max_length=500)
    expected_version: int = Field(ge=1)


class FeedbackInput(InputModel):
    feedback: str = Field(min_length=3, max_length=1500)
    expected_version: int = Field(ge=1)


class RollbackInput(InputModel):
    version: int = Field(ge=1)
    expected_version: int = Field(ge=1)
