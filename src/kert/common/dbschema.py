import sqlite3

SCHEMA_VERSION = "1"


def create_schema(conn: sqlite3.Connection) -> None:
    raise NotImplementedError
