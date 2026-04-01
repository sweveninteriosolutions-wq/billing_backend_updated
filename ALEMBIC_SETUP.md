## Alembic Setup Instructions

Alembic has NOT been initialized yet in this project.
To initialize it, run from the project root:

```bash
alembic init alembic
```

Then replace `alembic/env.py` with the async version below, and run:

```bash
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

### alembic/env.py (async version)
```python
import asyncio, os
from logging.config import fileConfig
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context
from dotenv import load_dotenv
load_dotenv()
from app.core.db import Base
import app.models  # registers all models
target_metadata = Base.metadata
DATABASE_URL = os.environ["DATABASE_URL"]

def run_migrations_offline():
    context.configure(url=DATABASE_URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations():
    engine = create_async_engine(DATABASE_URL, future=True)
    async with engine.connect() as conn:
        await conn.run_sync(do_run_migrations)
    await engine.dispose()

def run_migrations_online():
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```
