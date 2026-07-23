def get_priority(filename: str) -> int:
    ext = filename.lower().split('.')[-1]
    if ext == 'hwpx': return 1
    if ext == 'pdf': return 2
    if ext == 'hwp': return 3
    return 99