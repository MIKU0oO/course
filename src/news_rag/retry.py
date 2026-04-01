import time


def retry(retry: int = 3, sleep: int = 5):
    def decorator(func):
        def wrapper(*args, **kwargs):
            attempt = 0
            while attempt < retry:
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    attempt += 1
                    print(f"Retry {attempt}/{retry} failed: {exc}")
                    time.sleep(sleep)
            raise Exception(f"Failed after {retry} retries")

        return wrapper

    return decorator
