"""AccessMap API: public venue directory and reviewed community suggestions."""

from __future__ import annotations

import hmac
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env", override=False)
DB_PATH = Path(os.environ.get("ACCESSMAP_DB", ROOT / "accessmap.sqlite3"))
ADMIN_KEY = os.environ.get("ACCESSMAP_ADMIN_KEY", "")

app = FastAPI(
    title="AccessMap",
    description="Explore venue access details and submit evidence-backed corrections.",
    version="0.2.0",
)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@contextmanager
def database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    with database() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS places (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                area TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                step_free INTEGER,
                accessible_restroom INTEGER,
                transit TEXT NOT NULL,
                verification_status TEXT NOT NULL CHECK (verification_status IN ('demo', 'verified')),
                verification_source TEXT NOT NULL,
                verified_on TEXT,
                details TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                area TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                step_free INTEGER,
                accessible_restroom INTEGER,
                transit TEXT NOT NULL,
                evidence TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
                created_at TEXT NOT NULL,
                reviewed_at TEXT
            );
            """
        )
        total = conn.execute("SELECT COUNT(*) FROM places").fetchone()[0]
        if total == 0:
            now = datetime.now(timezone.utc).isoformat()
            demo_places = [
                ("Civic Hall Demo Venue", "Civil Lines", 25.4522, 81.8357, 1, 1, "High", "Illustrative sample data; not surveyed.", "Map position and access details are examples only."),
                ("Riverside Learning Space", "Daraganj", 25.4375, 81.8640, 0, 0, "Medium", "Illustrative sample data; not surveyed.", "Map position and access details are examples only."),
                ("University Forum Demo Venue", "George Town", 25.4460, 81.8478, 1, 0, "High", "Illustrative sample data; not surveyed.", "Map position and access details are examples only."),
                ("Community Studio Demo Venue", "Naini", 25.4025, 81.8821, 1, 0, "Low", "Illustrative sample data; not surveyed.", "Map position and access details are examples only."),
            ]
            conn.executemany(
                """INSERT INTO places
                   (name, area, latitude, longitude, step_free, accessible_restroom,
                    transit, verification_status, verification_source, details, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'demo', ?, ?, ?)""",
                [(*row, now) for row in demo_places],
            )


@app.on_event("startup")
def startup() -> None:
    initialize_database()


class Suggestion(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    area: str = Field(min_length=2, max_length=80)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    step_free: bool | None = None
    accessible_restroom: bool | None = None
    transit: Literal["High", "Medium", "Low", "Unknown"] = "Unknown"
    evidence: str = Field(min_length=8, max_length=500, description="Evidence source, such as an on-site visit or venue accessibility page.")
    details: str = Field(default="", max_length=1000)

    @field_validator("name", "area", "evidence", "details", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class ReviewDecision(BaseModel):
    decision: Literal["approve", "reject"]
    verification_source: str | None = Field(default=None, min_length=8, max_length=500)
    verified_on: date | None = None

    @field_validator("verification_source", mode="before")
    @classmethod
    def strip_source(cls, value):
        return value.strip() if isinstance(value, str) else value


def require_admin(provided_key: str | None) -> None:
    if not ADMIN_KEY:
        raise HTTPException(status_code=503, detail="Reviewing submissions is disabled until ACCESSMAP_ADMIN_KEY is configured.")
    if not provided_key or not hmac.compare_digest(provided_key, ADMIN_KEY):
        raise HTTPException(status_code=401, detail="A valid admin key is required.")


def as_bool(value):
    return None if value is None else bool(value)


@app.get("/")
def home():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/health")
def health():
    try:
        with database() as conn:
            conn.execute("SELECT 1").fetchone()
    except sqlite3.Error as error:
        raise HTTPException(status_code=503, detail="Database unavailable.") from error
    return {"status": "ok", "database": "ok"}


@app.get("/api/places")
def places(
    step_free: bool = False,
    restroom: bool = False,
    area: str = Query(default="", max_length=80),
    verification: Literal["all", "verified", "demo"] = "all",
):
    clauses, values = [], []
    if step_free:
        clauses.append("step_free = 1")
    if restroom:
        clauses.append("accessible_restroom = 1")
    if area.strip():
        clauses.append("area LIKE ? COLLATE NOCASE")
        values.append(f"%{area.strip()}%")
    if verification != "all":
        clauses.append("verification_status = ?")
        values.append(verification)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with database() as conn:
        rows = conn.execute(f"SELECT * FROM places{where} ORDER BY verification_status DESC, name", values).fetchall()
        counts = conn.execute("SELECT verification_status, COUNT(*) AS count FROM places GROUP BY verification_status").fetchall()
    summary = {row["verification_status"]: row["count"] for row in counts}
    return {
        "places": [
            {
                "id": row["id"], "name": row["name"], "area": row["area"],
                "lat": row["latitude"], "lon": row["longitude"],
                "step_free": as_bool(row["step_free"]), "accessible_restroom": as_bool(row["accessible_restroom"]),
                "transit": row["transit"], "verification_status": row["verification_status"],
                "verification_source": row["verification_source"], "verified_on": row["verified_on"],
                "details": row["details"],
            } for row in rows
        ],
        "counts": {"verified": summary.get("verified", 0), "demo": summary.get("demo", 0)},
    }


@app.post("/api/submissions", status_code=201)
def submit_suggestion(suggestion: Suggestion):
    now = datetime.now(timezone.utc).isoformat()
    with database() as conn:
        cursor = conn.execute(
            """INSERT INTO submissions
               (name, area, latitude, longitude, step_free, accessible_restroom, transit,
                evidence, details, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                suggestion.name, suggestion.area, suggestion.latitude, suggestion.longitude,
                None if suggestion.step_free is None else int(suggestion.step_free),
                None if suggestion.accessible_restroom is None else int(suggestion.accessible_restroom),
                suggestion.transit, suggestion.evidence, suggestion.details, now,
            ),
        )
        submission_id = cursor.lastrowid
    return {"id": submission_id, "status": "pending", "message": "Suggestion received. It will appear publicly only after review."}


@app.get("/api/admin/submissions")
def list_submissions(x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    with database() as conn:
        rows = conn.execute("SELECT * FROM submissions ORDER BY created_at DESC").fetchall()
    return {"submissions": [dict(row) for row in rows]}


@app.post("/api/admin/submissions/{submission_id}/review")
def review_submission(submission_id: int, decision: ReviewDecision, x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    if decision.decision == "approve" and (not decision.verification_source or not decision.verified_on):
        raise HTTPException(status_code=422, detail="Approval requires a verification source and verification date.")
    with database() as conn:
        row = conn.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Suggestion not found.")
        if row["status"] != "pending":
            raise HTTPException(status_code=409, detail="This suggestion has already been reviewed.")
        reviewed_at = datetime.now(timezone.utc).isoformat()
        if decision.decision == "approve":
            conn.execute(
                """INSERT INTO places
                   (name, area, latitude, longitude, step_free, accessible_restroom, transit,
                    verification_status, verification_source, verified_on, details, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'verified', ?, ?, ?, ?)""",
                (
                    row["name"], row["area"], row["latitude"], row["longitude"], row["step_free"],
                    row["accessible_restroom"], row["transit"], decision.verification_source,
                    decision.verified_on.isoformat(), row["details"], reviewed_at,
                ),
            )
        conn.execute("UPDATE submissions SET status = ?, reviewed_at = ? WHERE id = ?", ("approved" if decision.decision == "approve" else "rejected", reviewed_at, submission_id))
    return {"id": submission_id, "status": "approved" if decision.decision == "approve" else "rejected"}
