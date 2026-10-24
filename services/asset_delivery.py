"""Use a captured media snapshot even if its catalog entry is deleted meanwhile."""
import io
from contextlib import contextmanager

import discord


@contextmanager
def media_file(media):
    with io.BytesIO(media.data) as stream:
        attachment = discord.File(stream, filename=media.filename)
        try:
            yield attachment
        finally:
            attachment.close()
