"""Tools for adding material to the library and reading it in bounded, restartable batches."""
from .. import library, organization as org
from ..registry import P, tool


@tool('library_add', 'Add a connected file or folder to the library at once; its content is read afterwards in the background.', human=True,
      source=P('string', 'connection to add from', True), path=P('string', 'relative file or folder inside the connection'),
      folder=P('string', 'project, course or collection to place it in; omit for Inbox'))
def add(rec, source, path='', folder=''):
    org._parent(rec, folder)
    result = library.add(rec, source, path)
    if folder:
        org.move_many(rec, result['ids'], folder)
    return dict(result, counts=library.counts(rec))


@tool('library_process', 'Read the next few waiting library items so they become searchable; safe to call repeatedly.', writes=True,
      limit=P('integer', 'at most 25 items per call; default 8'))
def process(rec, limit=8):
    return library.process(rec, limit)


@tool('library_status', 'Count library items by progress: added, reading, ready and needing attention.')
def status(rec):
    return dict(library.counts(rec), remaining=len(library.pending(rec)))


@tool('library_retry', 'Read an item again, for example after fixing the file or reconnecting its folder.', human=True,
      subject=P('string', 'library item', True))
def retry(rec, subject):
    return library.retry(rec, subject)


@tool('library_forget', 'Remove an item from the library list. The original file and any cited history stay untouched.', human=True,
      subject=P('string', 'library item', True))
def forget(rec, subject):
    return library.forget(rec, subject)
