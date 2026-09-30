class DaemonUnavailableError(ConnectionError):
    """The daemon can't be reached: it didn't start, stopped, or the connection dropped and
    reconnecting failed."""
