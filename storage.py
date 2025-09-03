import os
from threading import Lock

SEEN_FILE = "/app/data/seen_hashes.txt"
lock = Lock()

def seen_before(hash_value: str) -> bool:
    """Check if a hash has been seen before and store new hashes."""
    os.makedirs(os.path.dirname(SEEN_FILE), exist_ok=True)  # Ensure directory exists
    with lock:
        try:
            if os.path.exists(SEEN_FILE):
                with open(SEEN_FILE, 'r') as f:
                    if hash_value in f.read().splitlines():
                        return True
            with open(SEEN_FILE, 'a') as f:
                f.write(hash_value + '\n')
            return False
        except Exception as e:
            print(f"[ERROR] Storage error: {e}")
            return False
