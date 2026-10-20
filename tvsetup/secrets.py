"""Pairing credentials may enter private payloads, never diagnostic records."""

from .common import Refused, sha


def pairing_record(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise Refused("Pairing configuration must be an object")
    result = dict(value)
    if "token" in result:
        token = result.pop("token")
        if not isinstance(token, str):
            raise Refused("Pairing token must be a string")
        result["token_sha256"] = sha(token.encode())
    return result
