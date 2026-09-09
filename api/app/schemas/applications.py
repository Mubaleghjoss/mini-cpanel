from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


EnvironmentKey = Literal["production", "staging"]
Classification = Literal["managed_application", "development_only", "system_tool"]


class EnvironmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment_key: EnvironmentKey
    runtime_path: str | None = None
    branch: str | None = None
    domain: str | None = None
    service_identifier: str | None = None
    read_only_default: bool | None = None

    @model_validator(mode="after")
    def apply_environment_default(self):
        if self.read_only_default is None:
            self.read_only_default = self.environment_key == "production"
        return self


class EnvironmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    environment_key: EnvironmentKey
    runtime_path: str | None
    branch: str | None
    domain: str | None
    service_identifier: str | None
    read_only_default: bool


class ApplicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*$")
    display_name: str = Field(min_length=1, max_length=200)
    source_path: str | None = None
    classification: Classification = "managed_application"
    environments: list[EnvironmentCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def environment_keys_are_unique(self):
        keys = [item.environment_key for item in self.environments]
        if len(keys) != len(set(keys)):
            raise ValueError("environment keys must be unique per application")
        return self


class ApplicationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    source_path: str | None = None
    classification: Classification | None = None
    environments: list[EnvironmentCreate] | None = None

    @model_validator(mode="after")
    def environment_keys_are_unique(self):
        if self.environments is not None:
            keys = [item.environment_key for item in self.environments]
            if len(keys) != len(set(keys)):
                raise ValueError("environment keys must be unique per application")
        return self


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    identity: str
    display_name: str
    source_path: str | None
    classification: Classification
    environments: list[EnvironmentResponse]
