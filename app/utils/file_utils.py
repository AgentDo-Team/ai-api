def get_priority(filename: str) -> int:
    """
    확장자 우선순위 결정 로직!
    hwpx(1순위) > pdf(2순위) > hwp(3순위). 그 외는 99(제외)
    """
    ext = filename.lower().split('.')[-1]
    if ext == 'hwpx': return 1
    if ext == 'pdf': return 2
    if ext == 'hwp': return 3
    return 99