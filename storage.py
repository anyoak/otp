seen_hashes = set()

def seen_before(h):
    if h in seen_hashes:
        return True
    seen_hashes.add(h)
    return False
