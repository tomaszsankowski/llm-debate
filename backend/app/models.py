from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

MODEL_ID = "qwen/qwen3.8-27b"
Level = Annotated[int, Field(ge=1, le=5, strict=True)]
RequiredText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=12000)
]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Traits(Model):
    escalation: Level = 3
    openness: Level = 3
    reactivity: Level = 3
    risk: Level = 3
    aggression: Level = 3
    dominance: Level = 3


class Agent(Model):
    name: ShortText
    role: RequiredText
    position: RequiredText
    goal: RequiredText
    instructions: str = Field(default="", max_length=12000)
    traits: Traits = Field(default_factory=Traits)
    max_tokens: int = Field(default=2048, ge=128, le=16384, strict=True)
    reasoning: bool = False


class DebateConfig(Model):
    name: ShortText = "Nowa debata"
    topic: RequiredText
    question: RequiredText
    context: str = Field(default="", max_length=24000)
    goal: RequiredText = "Wymiana argumentów i próba przekonania rozmówcy"
    first_speaker: Literal["A", "B", "random"] = "A"
    rounds: int = Field(default=10, ge=1, le=100, strict=True)
    opening: RequiredText = "Przedstaw swoje stanowisko i najważniejsze argumenty na jego poparcie."
    agents: tuple[Agent, Agent]

    @model_validator(mode="before")
    @classmethod
    def discard_legacy_word_target(cls, data):
        # Existing drafts and archived configurations remain reusable.
        if isinstance(data, dict) and "target_words" in data:
            return {key: value for key, value in data.items() if key != "target_words"}
        return data


class Annotation(Model):
    notes: str = Field(default="", max_length=20000)
    outcome: Literal["unrated", "consensus", "partial", "disagreement"] = "unrated"


class Control(Model):
    action: Literal["pause", "resume", "step", "stop"]
