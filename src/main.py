from fastapi import FastAPI

from routes import accounts_router, shopping_carts_router, orders_router, payments_router
from routes.cinema import cinema_router


app = FastAPI(
    title="Online Cinema",
    description="Description of project",
)

api_version_prefix = "/api/v1"

app.include_router(accounts_router, prefix=f"{api_version_prefix}/accounts", tags=["accounts"])
app.include_router(cinema_router, prefix=f"{api_version_prefix}/cinema", tags=["cinema"])
app.include_router(shopping_carts_router, prefix=f"{api_version_prefix}/shopping_carts", tags=["shopping_carts"])
app.include_router(orders_router, prefix=f"{api_version_prefix}/orders", tags=["orders"])
app.include_router(payments_router, prefix=f"{api_version_prefix}/payments", tags=["payments"])
