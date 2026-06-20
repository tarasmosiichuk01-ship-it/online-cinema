# 🎬 Online Cinema API

A high-performance, fully asynchronous RESTful API for a digital Online Cinema platform built with **FastAPI**. This project features a robust, decoupled architecture including interactive social tools (comments, ratings, reactions), a commerce ecosystem with **Stripe** payment processing, and automated background tasks.

---

## 🌟 Key Features

### 🔐 Security & Auth
* **JWT Authentication** — Secure double-token architecture using short-lived Access and long-lived Refresh tokens.
* **Email Activation** — User registration flow with rich HTML activation links valid for 24 hours.
* **Complexity Validation** — Enforced strict password policies requiring symbols, digits, and mixed cases.
* **Role-Based Access (RBAC)** — Hierarchical permission layers for `USER`, `MODERATOR`, and `ADMIN` groups.

### 🎬 Movie Catalog & Interactions
* **Advanced Catalog Engine** — Movie browsing with cursor pagination, multi-attribute filtering, sorting, and full-text search.
* **User Social Tools** — Like/dislike system, 10-point scale ratings, and dynamic "Favorites" list management.
* **Threaded Comments** — Deeply structured review system with native support for nested replies.
* **Instant Alerts** — Background worker email notifications triggered when your comment receives replies or likes.

### 🛒 Commerce & Payments
* **Shopping Cart** — Centralized item management that explicitly prevents duplicate movie purchases.
* **Order Tracking** — Multi-status orders (`pending`, `paid`, `canceled`) with historical price-freezing (`price_at_order`).
* **Stripe Integration** — Secure production checkout pipeline verified via automated cryptographic Webhooks.

### ⚙️ Background Tasks & Infrastructure
* **Dependency Engine** — Unified dependency and environment management handled via **Poetry** (`pyproject.toml`).
* **Celery Beat Scheduler** — Periodic workers automatically purging expired registration and reset tokens.
* **Fully Containerized** — Multi-container dockerized infrastructure orchestration (`app`, `db`, `redis`, `celery`, `celery_beat`, `mailhog`).

---

## 🚀 Running with Docker (Recommended)

### Prerequisites
- [Docker](https://docs.docker.com/get-docker/) >= 24.0
- [Docker Compose](https://docs.docker.com/compose/install/) >= 2.0

### 1. Clone the repository

```bash
git clone https://github.com/tarasmosiichuk01-ship-it/online-cinema.git
cd online-cinema
```

### 2. Create `.env` and `.env.test` files

Copy the examples and fill in your values:

```bash
cp .env.sample .env
cp .env.test.sample .env.test
```

### 3. Start all services

```bash
docker-compose up --build
```

The API will be available at: `http://localhost:8000`  
Interactive API docs (Swagger UI): `http://localhost:8000/docs`  
MailHog (email testing UI): `http://localhost:8025`

### Useful Docker commands

```bash
# Run in detached (background) mode
docker-compose up --build -d

# View logs
docker-compose logs -f

# View logs for a specific service
docker-compose logs -f app

# Stop all services
docker-compose down

# Stop and remove volumes (resets the database)
docker-compose down -v
```

---

## 🛠️ Running Locally (without Docker)

### Prerequisites
- Python >= 3.10
- [Poetry](https://python-poetry.org/docs/#installation)
- PostgreSQL
- Redis

### 1. Clone the repository

```bash
git clone https://github.com/tarasmosiichuk01-ship-it/online-cinema.git
cd online-cinema
```

### 2. Set up the environment

```bash
python -m venv venv
source venv/bin/activate  # macOS / Linux
venv\Scripts\activate     # Windows

pip install poetry
poetry install
```

### 3. Create `.env` and `.env.test` files

```bash
cp .env.sample .env
cp .env.test.sample .env.test
```

### 4. Apply database migrations

```bash
alembic upgrade head
```

### 5. Start the development server

```bash
uvicorn src.main:app --reload
```

The API will be available at: `http://localhost:8000`  
Interactive API docs (Swagger UI): `http://localhost:8000/docs`

### 6. Start Celery workers (optional, required for background tasks)

Open two additional terminals with the virtual environment activated:

```bash
# Worker
celery -A src.tasks.celery_app worker --loglevel=info

# Beat scheduler
celery -A src.tasks.celery_app beat --loglevel=info
```

---

## 🧪 Running Tests

```bash
# With Docker
docker-compose exec app pytest

# Locally
pytest
```