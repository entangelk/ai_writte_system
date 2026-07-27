"""Create a user (bootstrap the first admin before the admin API exists).

The admin API is a later slice (D8 step 5), so this is the only way to mint the
first account. Password is read from the AUTH_BOOTSTRAP_PASSWORD environment
variable rather than argv so it does not land in shell history or `ps` output.

    AUTH_BOOTSTRAP_PASSWORD='...' \
    CORE_SOT_MONGO_URI=mongodb://localhost:27520 \
    python3 scripts/create_user.py <username> [--admin]
"""

from __future__ import annotations

import os
import sys

from services.application.app.auth.password import Argon2PasswordHasher
from services.application.app.auth.users import DuplicateUsername, UserService
from services.application.app.auth.users_mongo import MongoUserRepository
from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    is_admin = "--admin" in argv[1:]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    username = args[0]

    password = os.environ.get("AUTH_BOOTSTRAP_PASSWORD")
    if not password:
        print("AUTH_BOOTSTRAP_PASSWORD is required", file=sys.stderr)
        return 2

    uri = os.environ.get("CORE_SOT_MONGO_URI")
    if not uri:
        # Refuse to run against the in-memory store: it would report success and
        # persist nothing.
        print("CORE_SOT_MONGO_URI is required", file=sys.stderr)
        return 2

    service = UserService(
        MongoUserRepository.from_uri(
            uri, db_name=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME)
        ),
        hasher=Argon2PasswordHasher(),
    )
    try:
        user = service.create_user(
            username=username, password=password, is_admin=is_admin
        )
    except DuplicateUsername:
        print(f"user already exists: {username}", file=sys.stderr)
        return 1
    print(f"created {user.id} username={user.username} is_admin={user.is_admin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
