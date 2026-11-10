"""Tools for logical workspace identity and qualified historical work membership."""
from .. import workspaces
from ..registry import P, tool


@tool('workspace_identity', 'The stable logical workspace and its distinct physical destination.',
      workspace_id=P('string', 'selected stable workspace id'))
def identity(rec, workspace_id=None):
    return workspaces.identity(rec, workspace_id)


@tool('workspace_identity_resolve', 'Resolve an existing workspace; ambiguity returns choices and never creates.',
      target=P('string', 'exact workspace id, hub id, record name or display title'),
      workspace_id=P('string', 'explicit selected workspace id'), kind=P('string', 'course, project, general or record'))
def resolve(rec, target=None, workspace_id=None, kind=None):
    return workspaces.resolve(rec, target, workspace_id, kind)


@tool('workspace_ensure', 'Explicitly create a workspace once by a stable key, or reuse General work.', human=True,
      kind=P('string', 'workspace kind', True, ('course', 'project', 'general')),
      title=P('string', 'initial display title', True), key=P('string', 'stable creation key independent of title', True))
def ensure(rec, kind, title, key):
    return workspaces.ensure(rec, kind, title, key)


@tool('workspace_member_assign', 'Assign reviewed qualified work to a workspace without moving or merging history.', human=True,
      workspace_id=P('string', 'selected stable workspace id', True),
      members=P('array', 'qualified references with optional group', True), assigned=P('boolean', 'false appends a compensating removal'))
def assign(rec, workspace_id, members, assigned=True):
    return workspaces.assign(rec, workspace_id, members, assigned)


@tool('workspace_overview', 'Grouped sessions, sources, handouts and research with physical ownership and provenance.',
      workspace_id=P('string', 'selected stable workspace id'))
def overview(rec, workspace_id=None):
    return workspaces.overview(rec, workspace_id)


@tool('workspace_work_resolve', 'Resolve a qualified historical work while retaining the selected logical workspace.',
      ref=P('object', 'owner_record, entity_id, optional actual revision', True), workspace_id=P('string', 'selected stable workspace id'))
def work_resolve(rec, ref, workspace_id=None):
    return workspaces.work_resolve(rec, ref, workspace_id)


@tool('capability_identity', 'Canonical capability reference and original evidence references; titles never imply equivalence.',
      ref=P('object', 'qualified capability reference', True))
def capability_identity(rec, ref):
    return workspaces.capability_identity(rec, ref)


@tool('capability_equivalence', 'Record a person-verified equivalence bound to both capability revisions.', human=True,
      alias=P('object', 'qualified alias with actual revision', True), canonical=P('object', 'qualified canonical capability with revision', True),
      evidence=P('string', 'verification and limitations', True), verified_by=P('string', 'person who verified equivalence', True))
def equivalence(rec, alias, canonical, evidence, verified_by):
    return workspaces.equivalence(rec, alias, canonical, evidence, verified_by)
