import os
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


@lru_cache
def session_factory():
    url = os.environ.get("RECOGNITION_DATABASE_URL")
    if not url:
        password = os.environ.get("RECOGNITION_DB_PASSWORD")
        if not password:
            raise RuntimeError("RECOGNITION_DATABASE_URL or RECOGNITION_DB_PASSWORD is required")
        url = URL.create("postgresql+psycopg", username=os.environ.get("RECOGNITION_DB_USER", "recognition_service_login"),
                         password=password, host=os.environ.get("DB_HOST", "database"),
                         port=int(os.environ.get("DB_PORT", "5432")), database=os.environ.get("DB_NAME", "thesis"))
    return sessionmaker(create_engine(url, pool_pre_ping=True), expire_on_commit=False)


def get_session():
    with session_factory()() as session:
        yield session
