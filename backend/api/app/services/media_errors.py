class MediaInspectionError(Exception):
    """The file is not valid audio in a supported format.

    Messages are for server-side diagnosis only and are never sent to clients.
    """
