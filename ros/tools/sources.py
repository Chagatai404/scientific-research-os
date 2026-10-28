"""Tools for scoped source connections, immutable passages and local previews."""
from .. import sources
from ..registry import tool, P

@tool('source_register', 'Connect a local file, folder, vault or codebase without scanning or executing it.', human=True,
      root=P('string', 'explicitly selected absolute local path', True), kind=P('string', 'connection kind', enum=('file', 'folder', 'vault', 'codebase')),
      label=P('string', 'display label'), local_only=P('boolean', 'block cloud disclosure; default true'))
def register(rec, root, kind='file', label='', local_only=True):
    return sources.register(rec, root, kind, label, local_only)

@tool('source_list', 'List source connections and their current availability without scanning their contents.')
def listing(rec):
    return [sources.public(row) for row in sources.connections(rec)]

@tool('source_children', 'Browse one directory lazily within an existing source connection.', source=P('string', 'connection id', True), path=P('string', 'relative folder'), offset=P('integer', 'page offset'), limit=P('integer', 'page size'))
def children(rec, source, path='', offset=0, limit=100):
    return sources.children(rec, source, path, offset, limit)

@tool('source_preview', 'Preview a local file or retained cited revision without executing its contents.', source=P('string', 'connection id', True), path=P('string', 'relative file'), revision=P('string', 'cited content hash'))
def preview(rec, source, path='', revision=None):
    return sources.preview(rec, source, path, revision)

@tool('source_capture', 'Retain an immutable source revision and capture a bounded passage with exact line locators.', writes=True, source=P('string', 'connection id', True), path=P('string', 'relative file'), start_line=P('integer', 'first line'), end_line=P('integer', 'last line'))
def capture(rec, source, path='', start_line=1, end_line=80):
    return sources.capture(rec, source, path, start_line, end_line)

@tool('source_change', 'Pause, resume or disconnect a source without deleting any original files.', human=True, source=P('string', 'connection id', True), action=P('string', 'action', True, ('remove', 'pause', 'resume')))
def change(rec, source, action):
    return sources.change(rec, source, action)

@tool('source_location', 'Resolve a connected local path for an explicit host open or reveal action.', human=True, source=P('string', 'connection id', True), path=P('string', 'relative file or folder'))
def location(rec, source, path=''):
    return {'path': str(sources.resolve(rec, source, path)), 'kind': sources.get(rec,source)['kind']}

@tool('source_report', 'Record a completed source engine report without modifying the original repository.', writes=True, source=P('string', 'connection id', True), result=P('object', 'engine report', True))
def report(rec, source, result):
    sources.get(rec, source)
    event = rec.append('source.report', source, {'result': result})
    return {'event': event['id']}

@tool('source_reports', 'Read saved understanding coverage reports for one connected codebase.', source=P('string', 'connection id', True))
def reports(rec, source):
    return [e['data']['result'] for e in rec.events(type='source.report', subject=source)][-10:]

@tool('source_index_batch', 'Incrementally index at most twenty approved source files in a rebuildable lexical cache.', writes=True, source=P('string', 'connection id', True), paths=P('array', 'relative paths', True), generation=P('string', 'index pass id', True))
def index_batch(rec, source, paths, generation): return sources.index_batch(rec, source, paths, generation)

@tool('source_search', 'Search an explicitly indexed connection with bounded local excerpts and source revisions.', q=P('string', 'query', True), source=P('string', 'connection id'), limit=P('integer', 'maximum matches'))
def search(rec, q, source=None, limit=30): return sources.search(rec, q, source, limit)

@tool('source_use_vault', 'Use a connected vault for Research OS projection without importing or synchronizing any notes.', human=True, source=P('string','vault connection id',True), folder=P('string','generated Research OS folder inside the vault'))
def use_vault(rec,source,folder='Research OS'): return sources.use_vault(rec,source,folder)

@tool('source_relocate', 'Explicitly relocate a connection while retaining its source and external record identity.', human=True, source=P('string','connection id',True), root=P('string','new explicitly selected absolute path',True))
def relocate(rec,source,root):return sources.relocate(rec,source,root)

@tool('source_protect_derived', 'Mark a record as containing local-only derived material; cloud turns remain blocked.', writes=True, origin=P('string','source record identity',True), run=P('string','originating run',True))
def protect_derived(rec,origin,run):
    event=rec.append('source.derived_private',run,{'origin':origin})
    return {'event':event['id'],'localOnly':True}

@tool('transcription_draft','Save a faithful transcription draft bound to an immutable scan revision; retain uncertainty and apparent mistakes.',writes=True,source=P('string','source id',True),path=P('string','relative scan path',True),revision=P('string','source revision',True),text=P('string','faithful LaTeX/Markdown draft',True),by=P('string','author'))
def transcription_draft(rec,source,path,revision,text,by='tutor'):return sources.transcribe_draft(rec,source,path,revision,text,by)

@tool('transcription_accept','Mark an exact transcription draft reviewed by a person; original scan and prior drafts remain unchanged.',human=True,draft=P('string','immutable draft event id',True),by=P('string','your name',True))
def transcription_accept(rec,draft,by):return sources.accept_transcription(rec,draft,by)

@tool('transcription_list','Read preserved scan transcription drafts and human review receipts.',source=P('string','source id',True))
def transcription_list(rec,source):return sources.transcriptions(rec,source)
