from fastapi import FastAPI

from routes import accounts_router
from routes.cinema import cinema_router

app = FastAPI(
    title="Online Cinema",
    description="Description of project",
)

api_version_prefix = "/api/v1"

app.include_router(accounts_router, prefix=f"{api_version_prefix}/accounts", tags=["accounts"])
app.include_router(cinema_router, prefix=f"{api_version_prefix}/cinema", tags=["cinema"])
