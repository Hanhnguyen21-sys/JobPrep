"""Shared normalized shape both ATS clients (greenhouse.py, lever.py)
return, so ingestion/runner.py can upsert Company/JobPosting without
caring which ATS a posting came from.
"""

from datetime import datetime

from pydantic import BaseModel


class NormalizedJobPosting(BaseModel):
    external_id: str
    title: str
    location: str | None = None
    description: str | None = None  # plain text, HTML stripped
    url: str | None = None
    source_updated_at: datetime | None = None
