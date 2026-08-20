from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, jobs, resumes, roadmaps, users
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title="JobPrep API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(resumes.router)
app.include_router(jobs.router)
app.include_router(roadmaps.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
