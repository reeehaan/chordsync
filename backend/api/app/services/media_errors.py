class MediaInspectionError(Exception):
    """The file is not valid audio in a supported format.

    The message is for server logs only and is never sent to clients.
    """
