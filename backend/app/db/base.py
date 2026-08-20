from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base. Import every model module in
    alembic/env.py so `Base.metadata` sees all tables for autogenerate.
    """
    pass