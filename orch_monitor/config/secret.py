"""Client secret w systemowym magazynie (keyring); nigdy w pliku ustawien."""

import keyring
from keyring.errors import PasswordDeleteError

SERVICE_NAME = "OrchMonitor"


def get_secret(client_id: str) -> str | None:
    return keyring.get_password(SERVICE_NAME, client_id)


def set_secret(client_id: str, secret: str) -> None:
    keyring.set_password(SERVICE_NAME, client_id, secret)


def delete_secret(client_id: str) -> bool:
    """Zwraca False, jesli sekretu nie bylo."""
    try:
        keyring.delete_password(SERVICE_NAME, client_id)
    except PasswordDeleteError:
        return False
    return True
