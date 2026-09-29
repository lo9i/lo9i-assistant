"""The user profile: one structured document per user."""

from typing import Literal

from langgraph.store.base import BaseStore
from pydantic import BaseModel, Field

Section = Literal["wants", "likes", "dislikes", "interests", "technical_level", "projects", "work"]

_KEY = "profile"


class Profile(BaseModel):
    wants: list[str] = Field(default_factory=list, description="What the user wants: goals and needs.")
    likes: list[str] = Field(default_factory=list, description="Things the user likes.")
    dislikes: list[str] = Field(default_factory=list, description="Things the user dislikes or wants avoided.")
    interests: list[str] = Field(default_factory=list, description="Topics the user is interested in.")
    technical_level: list[str] = Field(
        default_factory=list, description="How technical the user is, and in which areas."
    )
    projects: list[str] = Field(default_factory=list, description="Kinds of projects the user works on.")
    work: list[str] = Field(default_factory=list, description="The user's work: role, field, tools.")


def namespace(user_id: str) -> tuple[str, ...]:
    return ("profile", user_id)


async def load(store: BaseStore, user_id: str) -> Profile:
    item = await store.aget(namespace(user_id), _KEY)
    return Profile.model_validate(item.value) if item else Profile()


async def save(store: BaseStore, user_id: str, profile: Profile) -> None:
    await store.aput(namespace(user_id), _KEY, profile.model_dump())


def render(profile: Profile) -> str:
    lines = [f"- {_title(name)}: {'; '.join(items)}" for name, items in profile.model_dump().items() if items]
    return "\n".join(lines) or "(empty so far)"


def _title(section: str) -> str:
    return section.replace("_", " ").capitalize()
