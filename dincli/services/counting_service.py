import time


def run_counting(count: int = 10, delay: float = 1.0) -> str:
    """Count from 1 to count (0 = infinite), printing 'Worker Counting: N' each step."""
    n = 0
    try:
        while count == 0 or n < count:
            n += 1
            print(f"Worker Counting: {n}", flush=True)
            time.sleep(delay)
    except KeyboardInterrupt:
        pass
    return f"Counted to {n}"
