"""
API Key Manager - Secure encryption and validation for API keys.
Uses Fernet symmetric encryption to store keys safely.
"""
import base64
import hashlib
import os
import secrets
import tempfile
from pathlib import Path
from threading import Lock
from typing import Optional

from cryptography.fernet import Fernet

# Location for encrypted keys file (stored outside project directory)
_CONFIG_DIR = Path.home() / ".config" / "patchwork-tutor"
_ENC_KEYS_FILE = _CONFIG_DIR / "keys.enc"
_KEY_FILE = _CONFIG_DIR / ".master.key"

_ENV_LOCK = Lock()


def _get_or_create_master_key() -> bytes:
    """Get existing master key or create a new one."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    if _KEY_FILE.exists():
        try:
            return _KEY_FILE.read_bytes()
        except Exception:
            pass
    
    # Generate a new master key
    master_key = Fernet.generate_key()
    _KEY_FILE.write_bytes(master_key)
    # Restrict permissions (Unix-like systems)
    try:
        os.chmod(_KEY_FILE, 0o600)
    except Exception:
        pass
    return master_key


def _get_fernet() -> Fernet:
    """Get Fernet instance with master key."""
    master_key = _get_or_create_master_key()
    # Derive a valid Fernet key from master key
    derived = hashlib.sha256(master_key).digest()
    fernet_key = base64.urlsafe_b64encode(derived)
    return Fernet(fernet_key)


def _load_encrypted_keys() -> dict[str, str]:
    """Load and decrypt keys from file."""
    if not _ENC_KEYS_FILE.exists():
        return {}
    
    try:
        encrypted_data = _ENC_KEYS_FILE.read_bytes()
        fernet = _get_fernet()
        decrypted = fernet.decrypt(encrypted_data)
        import json
        return json.loads(decrypted.decode('utf-8'))
    except Exception:
        # If decryption fails, file might be corrupted - start fresh
        return {}


def _save_encrypted_keys(keys: dict[str, str]) -> None:
    """Encrypt and save keys to file."""
    with _ENV_LOCK:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        import json
        data = json.dumps(keys).encode('utf-8')
        fernet = _get_fernet()
        encrypted = fernet.encrypt(data)
        
        # Write atomically using temp file
        fd, tmp_path = tempfile.mkstemp(
            prefix='keys-',
            suffix='.enc',
            dir=str(_CONFIG_DIR)
        )
        try:
            os.write(fd, encrypted)
            os.fsync(fd)
            os.close(fd)
            os.replace(tmp_path, _ENC_KEYS_FILE)
            try:
                os.chmod(_ENC_KEYS_FILE, 0o600)
            except Exception:
                pass
        except Exception:
            try:
                os.close(fd)
                os.unlink(tmp_path)
            except Exception:
                pass
            raise


def store_api_key(provider: str, key: str) -> None:
    """Store an encrypted API key for a provider."""
    keys = _load_encrypted_keys()
    keys[f"{provider}_api_key"] = key
    _save_encrypted_keys(keys)


def get_api_key(provider: str) -> Optional[str]:
    """Retrieve a decrypted API key for a provider."""
    keys = _load_encrypted_keys()
    return keys.get(f"{provider}_api_key")


def delete_api_key(provider: str) -> bool:
    """Delete an API key for a provider. Returns True if key was deleted."""
    keys = _load_encrypted_keys()
    key_name = f"{provider}_api_key"
    if key_name in keys:
        del keys[key_name]
        _save_encrypted_keys(keys)
        return True
    return False


def has_api_key(provider: str) -> bool:
    """Check if an API key exists for a provider."""
    keys = _load_encrypted_keys()
    return f"{provider}_api_key" in keys


def list_providers_with_keys() -> list[str]:
    """List all providers that have stored keys."""
    keys = _load_encrypted_keys()
    providers = []
    for key_name in keys:
        if key_name.endswith("_api_key"):
            providers.append(key_name.replace("_api_key", ""))
    return providers


def mask_api_key(key: str) -> str:
    """Mask an API key for safe display (show first 4 and last 4 chars)."""
    if not key or len(key) <= 8:
        return "****"
    return f"{key[:4]}...{key[-4:]}"


def validate_api_key_format(provider: str, key: str) -> tuple[bool, Optional[str]]:
    """
    Validate API key format based on provider requirements.
    Returns (is_valid, error_message).
    """
    if not key or not key.strip():
        return False, "API key cannot be empty"
    
    key = key.strip()
    
    # Length checks
    if len(key) < 10:
        return False, "API key is too short"
    
    # Provider-specific validation
    if provider == "openai":
        if not key.startswith("sk-"):
            return False, "OpenAI keys start with 'sk-'"
        if len(key) < 40:
            return False, "OpenAI key appears to be invalid"
    
    elif provider == "anthropic":
        if not key.startswith("sk-ant-"):
            return False, "Anthropic keys start with 'sk-ant-'"
        if len(key) < 50:
            return False, "Anthropic key appears to be invalid"
    
    elif provider == "openrouter":
        if not key.startswith("sk-or-"):
            return False, "OpenRouter keys start with 'sk-or-'"
        if len(key) < 50:
            return False, "OpenRouter key appears to be invalid"
    
    elif provider == "gemini":
        if len(key) < 30:
            return False, "Gemini API key appears to be invalid"
        # Gemini keys are usually alphanumeric with some special chars
        if not key.replace("-", "").replace("_", "").isalnum():
            return False, "Gemini API key contains invalid characters"
    
    return True, None
