"""Optional reflection tools. All observations are computed from owner-entered records."""

from datetime import date, timedelta
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, HttpUrl, model_validator

from .daily_routine_settings import Strict


class Prediction(Strict):
    key: UUID
    claim: str = Field(min_length=1, max_length=500)
    domain: str = Field(min_length=1, max_length=80)
    kind: Literal["binary", "duration", "quantity"] = "binary"
    probability: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    estimate: float | None = Field(default=None, allow_inf_nan=False)
    due_date: date
    gut_note: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def check_values(self):
        if self.kind == "binary" and (self.probability is None or self.estimate is not None):
            raise ValueError("Binary predictions need one probability.")
        if self.kind != "binary" and (self.estimate is None or self.probability is not None):
            raise ValueError("Enter an expected value for this prediction.")
        if self.kind == "duration" and self.estimate <= 0:
            raise ValueError("Duration estimates must be positive.")
        return self


class Resolution(Strict):
    result: bool | None = None
    actual: float | None = Field(default=None, allow_inf_nan=False)


def add_prediction(db, body):
    row = db.execute(
        "INSERT INTO app.routine_predictions(id,domain,claim,gut_note,kind,probability,estimate,due_date) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING RETURNING id",
        (
            body.key,
            body.domain,
            body.claim,
            body.gut_note,
            body.kind,
            body.probability,
            body.estimate,
            body.due_date,
        ),
    ).fetchone()
    if not row:
        saved = db.execute(
            "SELECT domain,claim,gut_note,kind,probability::float8 AS probability,"
            "estimate::float8 AS estimate,due_date FROM app.routine_predictions WHERE id=%s",
            (body.key,),
        ).fetchone()
        if saved != body.model_dump(exclude={"key"}):
            raise HTTPException(409, "This prediction was already saved with different content.")
    return {"id": body.key}


def resolve(db, identifier, body):
    row = db.execute(
        "SELECT * FROM app.routine_predictions WHERE id=%s FOR UPDATE", (identifier,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Prediction not found.")
    binary = row["kind"] == "binary"
    if (
        binary != (body.result is not None)
        or binary == (body.actual is not None)
        or (row["kind"] == "duration" and body.actual < 0)
    ):
        raise HTTPException(422, "Enter the outcome in the original prediction's units.")
    if row["resolved_at"]:
        if (
            row["result"] != body.result
            or (float(row["actual"]) if row["actual"] is not None else None) != body.actual
        ):
            raise HTTPException(409, "An outcome has already been recorded.")
    else:
        db.execute(
            "UPDATE app.routine_predictions SET result=%s,actual=%s,resolved_at=now() WHERE id=%s",
            (body.result, body.actual, identifier),
        )
    return {"id": identifier, "resolved": True}


def calibration(db):
    # ASSUMPTION: reveal Brier averages only after twenty resolved binary forecasts in one domain.
    return db.execute("""WITH samples AS (
      SELECT domain,least(3,floor(probability*4))::int AS bin, result::int AS hit,
             power(probability-result::int,2) AS error, count(*) OVER(PARTITION BY domain) AS n
      FROM app.routine_predictions WHERE kind='binary' AND resolved_at IS NOT NULL)
      SELECT domain,bin,count(*) AS samples,sum(hit) AS hits,
        CASE WHEN max(n)>=20 THEN round(avg(error),3) END AS brier
      FROM samples GROUP BY domain,bin ORDER BY domain,bin""").fetchall()


class PoolItem(Strict):
    kind: Literal["spark", "wildcard", "opportunity"]
    title: str = Field(min_length=1, max_length=180)
    source_url: HttpUrl | None = None
    relevance: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def check_link(self):
        if self.kind == "opportunity" and (not self.source_url or not self.relevance):
            raise ValueError("Give the link and its relevance to a goal.")
        return self


def habit_data(db, day, zone):
    from .planning import day_bounds

    start, end = day_bounds(day - timedelta(days=90), day, zone)
    return db.execute(
        """SELECT t.id,t.title,(t.completed_at AT TIME ZONE %s)::date AS day,
        sum(extract(epoch FROM (s.ended_at-s.started_at)))/60/t.estimated_minutes AS ratio
        FROM app.execution_sessions s JOIN app.tasks t ON t.id=s.task_id WHERE t.completed_at>=%s
        AND t.completed_at<%s AND s.ended_at IS NOT NULL GROUP BY t.id ORDER BY t.completed_at""",
        (zone, start, end),
    ).fetchall()


def propose_pattern(db, day, rows):
    # ASSUMPTION: one behavioral hypothesis per week, with evidence spanning at least two weeks.
    pattern = "Time spent on completed tasks exceeded your estimates"
    above = [r for r in rows if r["ratio"] > 1]
    if len(above) < 5 or (above[-1]["day"] - above[0]["day"]).days < 14:
        return
    if db.execute(
        "SELECT 1 FROM app.routine_hypotheses WHERE pattern=%s "
        "AND state IN ('proposed','confirmed','rejected')",
        (pattern,),
    ).fetchone():
        return
    db.execute(
        "INSERT INTO app.routine_hypotheses(pattern,week,evidence,counterexamples) VALUES(%s,%s,%s,%s) "
        "ON CONFLICT(week) DO NOTHING",
        (
            pattern,
            day - timedelta(days=day.weekday()),
            [r["id"] for r in above][-10:],
            [r["id"] for r in rows if r["ratio"] <= 1][-5:],
        ),
    )
