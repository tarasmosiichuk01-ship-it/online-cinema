#!/bin/sh

# Stop execution if any command fails
set -e

ALEMBIC_CONFIG="/app/alembic.ini"
MIGRATIONS_DIR="/app/alembic/versions"

echo "🔍 Checking database and migrations status..."

# Check if the migrations folder exists, if not, create it
if [ ! -d "$MIGRATIONS_DIR" ]; then
    echo "📁 Migrations folder does not exist. Creating it..."
    mkdir -p "$MIGRATIONS_DIR"
fi

# Check if the versions folder is empty
if [ -z "$(ls -A "$MIGRATIONS_DIR" 2>/dev/null)" ]; then
    echo "🆕 No migration files found at all. Assuming fresh setup..."
    echo "🆕 Generating initial migration..."
    poetry run alembic -c $ALEMBIC_CONFIG revision --autogenerate -m "initial_migration"

    echo "⚙️ Applying initial migration to the database..."
    poetry run alembic -c $ALEMBIC_CONFIG upgrade head

    echo "🌱 Running seed.py for fresh database..."
    poetry run python -m src.utils.seed
    echo "✅ Seeding completed."
else
    echo "🔄 Existing migrations found. Applying updates to head..."
    poetry run alembic -c $ALEMBIC_CONFIG upgrade head

    # --- CHECK FOR CHANGES IN THE MODELS ---
    echo "🔄 Generating temporary migration to detect model changes..."
    if ! poetry run alembic -c $ALEMBIC_CONFIG revision --autogenerate -m "temp_migration"; then
        echo "❌ Error generating temporary migration. Exiting."
        exit 1
    fi

    # Find the last created migration file
    LAST_MIGRATION=$(ls -t "$MIGRATIONS_DIR"/*.py 2>/dev/null | head -n 1)

    # Check if the migration is empty
    if [ -f "$LAST_MIGRATION" ] && grep -q "def upgrade() -> None:" "$LAST_MIGRATION" && grep -A 2 "def upgrade() -> None:" "$LAST_MIGRATION" | grep -q "pass"; then
        echo "👌 No changes detected in models. Deleting temporary migration file."
        rm "$LAST_MIGRATION"
    else
        echo "✨ Real changes detected! Applying new migration..."
        poetry run alembic -c $ALEMBIC_CONFIG upgrade head
    fi

    # Run the idempotent seeder check
    echo "🌱 Running idempotent seed.py check..."
    poetry run python -m src.utils.seed
fi

# Launch the FastAPI application itself
echo "🔥 Starting FastAPI server..."
exec poetry run uvicorn src.main:app --host 0.0.0.0 --port 8000