import os
import sys
import time

import psycopg2


def main():
    host = os.getenv("DB_HOST", "db")
    port = int(os.getenv("DB_PORT", "5432"))
    dbname = os.getenv("DB_NAME", "pet_project_db")
    user = os.getenv("DB_USER", "pet_admin")
    password = os.getenv("DB_PASSWORD", "")
    timeout_seconds = int(os.getenv("DB_WAIT_TIMEOUT", "90"))

    deadline = time.monotonic() + timeout_seconds
    last_error = None

    while time.monotonic() < deadline:
        try:
            connection = psycopg2.connect(
                host=host,
                port=port,
                dbname=dbname,
                user=user,
                password=password,
                connect_timeout=5,
            )
            connection.close()
            print(f"Database is ready at {host}:{port}/{dbname}")
            return 0
        except psycopg2.OperationalError as exc:
            last_error = exc
            print(f"Waiting for database {host}:{port}/{dbname}: {exc}", flush=True)
            time.sleep(2)

    print(f"Database did not become ready within {timeout_seconds} seconds: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
