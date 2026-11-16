"""Application DTOs. No imports or contracts with Lia's Brain."""

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Zoned(Model):
    timezone: str = "Europe/Berlin"

    @field_validator("timezone")
    @classmethod
    def named_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("Choose a valid named timezone, such as Europe/Berlin.") from None
        return value


class TaskInput(Zoned):
    title: str = Field(min_length=1, max_length=180)
    objective: str = Field(min_length=1, max_length=2000)
    description: str = Field(default="", max_length=10000)
    area: str = Field(default="work", min_length=1, max_length=100)
    due_date: date | None = None
    deadline_at: datetime | None = None
    priority: int = Field(default=2, ge=1, le=3, strict=True)
    estimated_minutes: int = Field(default=30, ge=1, le=1440, strict=True)
    effort: Literal["unspecified", "light", "moderate", "demanding"] = "unspecified"
    tags: list[str] = Field(default_factory=list, max_length=30)
    goal_id: UUID | None = None
    project_id: UUID | None = None
    parent_id: UUID | None = None
    dependencies: list[UUID] = Field(default_factory=list, max_length=100)

    @field_validator("tags")
    @classmethod
    def tags_valid(cls, values):
        if any(not value.strip() or len(value) > 60 for value in values):
            raise ValueError("Tags must contain 1–60 characters.")
        return list(dict.fromkeys(value.strip() for value in values))

    @field_validator("deadline_at")
    @classmethod
    def aware_deadline(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Deadline timestamp requires an explicit UTC offset.")
        return value


class GroupInput(Model):
    title: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=2000)
    goal_id: UUID | None = None


class RoutineInput(Zoned):
    title: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=2000)
    objective: str = Field(min_length=1, max_length=2000)
    area: str = Field(default="health", min_length=1, max_length=100)
    frequency: Literal["daily", "weekly"] = "daily"
    interval_count: int = Field(default=1, ge=1, le=52, strict=True)
    weekdays: list[int] = Field(default_factory=lambda: list(range(7)), min_length=1, max_length=7)
    starts_on: date
    ends_on: date | None = None
    window_start: time
    window_end: time
    expected_minutes: int = Field(default=30, ge=1, le=1440, strict=True)
    priority: int = Field(default=2, ge=1, le=3, strict=True)
    goal_id: UUID | None = None
    essential: bool = Field(default=False, strict=True)
    active: bool = Field(default=True, strict=True)

    @model_validator(mode="after")
    def valid_rule(self):
        if any(type(d) is not int or not 0 <= d <= 6 for d in self.weekdays):
            raise ValueError("Weekdays must be Monday=0 through Sunday=6.")
        if self.window_start.tzinfo or self.window_end.tzinfo:
            raise ValueError("Routine window uses local wall times and its named timezone.")
        if self.window_end <= self.window_start:
            raise ValueError("Routine window must end after its start on the same day.")
        if self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("Routine end must not precede its start.")
        return self


class TimeInput(Zoned):
    start: datetime
    end: datetime | None = None
    duration_minutes: float | None = Field(default=None, gt=0, le=10080, allow_inf_nan=False)
    fold: Literal[0, 1] = 0
    end_fold: Literal[0, 1] = 0
    reason: str = Field(default="Manually scheduled", min_length=1, max_length=1000)
    task_id: UUID | None = None
    title: str = Field(default="", max_length=180)
    description: str = Field(default="", max_length=2000)


class DateRange(Zoned):
    start: date
    end: date

    @model_validator(mode="after")
    def bounded(self):
        if not 0 <= (self.end - self.start).days <= 62:
            raise ValueError("Choose a date range of at most 63 days.")
        return self


class DailyInput(Zoned):
    day: date
    available_minutes: int = Field(ge=0, le=1440, strict=True)
    energy: str = Field(default="", max_length=100)
    focus: str = Field(default="", max_length=100)
    sleep: str = Field(default="", max_length=200)
    intention: str = Field(default="", max_length=2000)
    reflection: str = Field(default="", max_length=2000)
    confirm: bool = False
    review: bool = False


class ExecutionInput(Model):
    action: Literal["start", "pause", "resume", "complete", "progress", "reopen", "push"]
    percent: int | None = Field(default=None, ge=0, le=100, strict=True)
    block_id: UUID | None = None


class SplitInput(Model):
    at: datetime


class FocusSwitchInput(Model):
    from_task_id: UUID | None = None
    from_version: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode="after")
    def paired_source(self):
        if (self.from_task_id is None) != (self.from_version is None):
            raise ValueError("Provide both the previous focus task and its version.")
        return self


class ExceptionInput(Model):
    day: date


class AcknowledgeInput(Model):
    reminder_id: str = Field(min_length=1, max_length=200)


class Command(Model):
    key: UUID
    op: Literal[
        "task.create",
        "task.update",
        "task.execute",
        "focus.switch",
        "goal.create",
        "goal.update",
        "project.create",
        "project.update",
        "routine.create",
        "routine.update",
        "routine.skip",
        "ensure",
        "block.create",
        "block.update",
        "block.remove",
        "block.split",
        "event.create",
        "event.update",
        "event.remove",
        "daily.save",
        "reminder.ack",
    ]
    id: UUID | None = None
    version: int | None = Field(default=None, ge=1, strict=True)
    data: dict = Field(default_factory=dict)
