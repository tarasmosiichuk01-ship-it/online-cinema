from fastapi import FastAPI

from routes import accounts_router, movies_router

app = FastAPI(
    title="Online Cinema",
    description="Description of project",
)

api_version_prefix = "/api/v1"

app.include_router(accounts_router, prefix=f"{api_version_prefix}/accounts", tags=["accounts"])
app.include_router(movies_router, prefix=f"{api_version_prefix}/cinema", tags=["cinema"])

