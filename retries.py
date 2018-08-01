class RetryException(Exception):
    pass


"""
This file should provide some decorators to allow for easy retries when RetryException is raised

For example:
@retry(3)
@retryWithBackoff(?)
"""
