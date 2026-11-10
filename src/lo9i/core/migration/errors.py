class MigrationError(Exception):
    """An export or an import can't be done: a wrong password, a damaged file, a home that can't be read or written."""


class HomeInUseError(MigrationError):
    """The import would replace data this computer already has; it goes ahead only when asked to replace it."""
