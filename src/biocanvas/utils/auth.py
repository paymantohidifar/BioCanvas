# biocanvas/utils/auth.py
"""Passcode hashing and verification utilities."""
import os
import json
import hashlib
import hmac
import secrets
from typing import Dict
import logging

logger = logging.getLogger(__name__)


def hash_passcode(passcode: str) -> str:
    """Hashes a passcode using PBKDF2-HMAC-SHA256 with a random salt.

    This is a one-time developer utility. Run it once per passcode and store
    the returned string in PROJECT_LIST in core.py. Never store the plaintext
    passcode in source code.

    Args:
        passcode: The plaintext passcode to hash.

    Returns:
        A 'salt:hash' string where both parts are hex-encoded. Safe to store
        in source code.

    Example:
        >>> hash_passcode('my_secret')
        'a3f1c2...:9c2b47...'
    """
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac('sha256', passcode.encode('utf-8'), salt.encode('utf-8'), 100_000)
    return f"{salt}:{key.hex()}"


def verify_passcode(stored_hash: str, passcode: str) -> bool:
    """Verifies a plaintext passcode against a stored PBKDF2-HMAC-SHA256 hash.

    Uses hmac.compare_digest to prevent timing-based side-channel attacks.

    Args:
        stored_hash: The 'salt:hash' string produced by hash_passcode.
        passcode: The plaintext passcode entered by the user.

    Returns:
        True if the passcode matches the stored hash, False otherwise.
    """
    try:
        salt, key_hex = stored_hash.split(':', 1)
        new_key = hashlib.pbkdf2_hmac('sha256', passcode.encode('utf-8'), salt.encode('utf-8'), 100_000)
        return hmac.compare_digest(new_key.hex(), key_hex)
    except Exception:
        return False


def load_passcode_hashes(filepath: str) -> Dict[str, str]:
    """Loads project passcode hashes from a JSON file.

    The JSON file must contain a flat mapping of project names to
    'salt:hash' strings produced by hash_passcode().

    Args:
        filepath: Absolute or relative path to the JSON file.

    Returns:
        Dict mapping project name to stored hash string.

    Raises:
        FileNotFoundError: If the file does not exist. Generate hashes
            with hash_passcode() and create the file at the expected path.
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(
            f"Passcode hash file not found: '{filepath}'. "
            "Generate hashes with utils.hash_passcode() and create the file."
        )
    with open(filepath, 'r') as f:
        hashes: Dict[str, str] = json.load(f)
    logger.info("Loaded passcode hashes from '%s'", filepath)
    return hashes
