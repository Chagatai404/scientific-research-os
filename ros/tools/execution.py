"""Tools for provider capability profiles, custom agent manifests and explicit notebook execution permissions."""
from .. import execution, sources
from ..registry import tool, P, TOOLS

def _human():
    """The person-only tools, which no custom agent manifest may hold (the domain cannot read the registry)."""
    return frozenset(name for name, row in TOOLS.items() if row.human)

@tool('provider_profiles', 'List explicitly configured model profiles (subscription CLI, local loopback, remote HTTPS API) with their declared capabilities and credential reference, never a key.')
def profiles(rec): return execution.profiles(rec)

@tool('provider_configure', 'Save an explicit model connection and capability profile without invoking inference. A remote API profile stores a credential reference (environment variable or OS credential store name), never the key.', human=True, provider=P('string', 'provider transport', True, ('ollama', 'compatible','codex','claude','api')), endpoint=P('string', 'HTTP loopback endpoint, https:// remote API endpoint, or empty for native CLI', True), model=P('string', 'installed or explicitly configured model id', True), tools=P('boolean', 'user-verified tool calling support'), vision=P('boolean', 'user-verified vision support'), context_limit=P('integer', 'context character budget'), credential=P('object', 'credential reference {"store": "env"|"os", "name"}; never the key itself'), token_param=P('string', 'reply-length field the API expects; default chosen from the endpoint', enum=('max_tokens', 'max_completion_tokens')))
def configure(rec, provider, endpoint, model, tools=False, vision=False, context_limit=16000, credential=None, token_param=None): return execution.configure(rec, provider, endpoint, model, tools, vision, context_limit, credential, token_param)

@tool('provider_capabilities', 'Read what each provider adapter can do and on what evidence (declared, tested, live-verified), and what each configured profile declares.')
def capabilities(rec): return execution.capabilities(rec)

@tool('agent_list', "List the person's custom agent manifests (id, version, hash, base grant, tools, profile, limits), without their instructions.")
def agent_list(rec): return execution.agents(rec)

@tool('agent_define', "Save a custom agent manifest (a person's act). It can only narrow a base role or mode grant, never hold a person-only tool or a credential, and a version is immutable.", human=True, manifest=P('object', 'ros.agent-manifest.v1: id agent:<name>, version, title, instructions, base, tools, profile, result_schema, limits, requires', True))
def agent_define(rec, manifest): return execution.agent_define(rec, manifest, _human())

@tool('agent_get', "Read one custom agent manifest (newest version unless one is named) and whether its hash and rules still verify.", agent=P('string', 'agent:<name>', True), version=P('integer', 'manifest version'))
def agent_get(rec, agent, version=None): return execution.agent_get(rec, agent, version, _human())

@tool('agent_dispatch', 'The verified manifest of a custom agent with its system prompt and narrowed tools, for the runtime that runs it; refuses a manifest that does not verify.', agent=P('string', 'agent:<name>', True), brief=P('string', 'the work for the agent', True), version=P('integer', 'manifest version'))
def agent_dispatch(rec, agent, brief, version=None): return execution.agent_dispatch(rec, agent, brief, version, _human())

@tool('notebook_request', 'Request a committed scratch notebook trace or bounded mutation; execution is an explicit human permission.', human=True, source=P('string', 'connected codebase id', True), path=P('string', 'relative notebook path', True), by=P('string', 'your name', True), reason=P('string', 'why this notebook may run', True), mutation=P('object', 'one bounded source or cell mutation'), execute=P('boolean', 'actually execute; false means dry run'), groups=P('array', 'approved dependency groups'), timeout=P('integer', 'per notebook timeout in seconds'))
def request(rec, source, path, by, reason, mutation=None, execute=False, groups=None, timeout=600): return execution.notebook_request(rec, source, path, by, reason, mutation, execute, groups, timeout)

@tool('notebook_jobs', 'Inspect notebook requests, execution permissions and stored versus fresh output results.')
def jobs(rec): return execution.notebook_jobs(rec)

@tool('notebook_start', 'Claim a queued notebook request exactly once before starting its external process.', writes=True, request=P('string','request id',True))
def start(rec,request):return execution.notebook_start(rec,request)

@tool('notebook_result', 'Record an actual notebook worker result idempotently against its request.', writes=True, request=P('string', 'request id', True), result=P('object', 'worker result', True))
def result(rec, request, result): return execution.notebook_result(rec, request, result)

@tool('source_engine_root', 'Resolve a registered codebase for an explicitly requested local engine job.', human=True, source=P('string', 'connection id', True))
def engine_root(rec, source):
    row = sources.get(rec, source)
    if row['kind'] != 'codebase': raise ValueError('this source is not a codebase')
    return {'root': str(sources.resolve(rec, source))}

@tool('execution_limits', 'Read workspace context, output, step, deadline, queue and local provider-call budgets.')
def limits(rec):return execution.limits(rec)

@tool('execution_configure', 'Set conservative workspace execution budgets. Native CLI internal inference calls are not a spend cap.', human=True, values=P('object','context characters, output tokens, tool_steps, deadline seconds, queue and provider_calls',True))
def configure_limits(rec,values):return execution.configure_limits(rec,values)

@tool('vision_permission','Grant one turn permission for this exact retained image/PDF and configured destination. Local-only sources remain blocked.',human=True,source=P('string','source id',True),path=P('string','relative attachment path',True),revision=P('string','immutable attachment revision',True),model=P('string','exact configured vision model',True))
def vision_permission(rec,source,path,revision,model):return execution.vision_permission(rec,source,path,revision,model)

@tool('vision_dispatch_check','Check a consumed media permission still matches its exact queued turn and configured destination.',request=P('string','turn request id',True),model=P('string','destination model',True),permissions=P('array','one-shot permission event ids',True))
def vision_dispatch_check(rec,request,model,permissions):return execution.dispatch_vision(rec,permissions,request,model)

@tool('literature_search','Search public scholarly metadata. Queries leave this computer; candidates are not verified scientific evidence.',writes=True,query=P('string','public search query',True),engine=P('string','metadata service',enum=('crossref','europepmc')),limit=P('integer','1–20 results'))
def literature_search(rec,query,engine='crossref',limit=8):return execution.literature_search(rec,query,engine,limit)

@tool('compute_stage','Stage code and immutable inputs as a proposed experiment; does not execute or change the original codebase.',writes=True,experiment=P('string','experiment:<key>',True),files=P('object','safe relative text files',True),argv=P('array','python/Rscript/julia argv, no shell',True),inputs=P('array','captured source references'),timeout=P('integer','1–600 seconds'))
def stage(rec,experiment,files,argv,inputs=None,timeout=120):return execution.stage(rec,experiment,files,argv,inputs,timeout)

@tool('compute_staged','Read the exact latest staged code and execution proposal.',experiment=P('string','experiment id',True))
def staged(rec,experiment):return execution.staged(rec,experiment)

@tool('compute_request','Grant execution permission for an already human-approved exact staged plan. Trusted native code runs in a disposable directory, not an OS sandbox.',human=True,experiment=P('string','experiment id',True),by=P('string','your name',True),reason=P('string','execution reason',True))
def compute_request(rec,experiment,by,reason):return execution.compute_request(rec,experiment,by,reason)

@tool('operation_list','Read actual scholarly retrieval and compute operation states and saved manifests.')
def operations(rec):return [{k:v for k,v in r.items() if k!='packet'} for r in execution.operations(rec)]

@tool('operation_start','Claim a queued operation once and return its bound engine packet.',writes=True,identifier=P('string','operation id',True))
def operation_start(rec,identifier):return execution.operation_start(rec,identifier)

@tool('operation_finish','Persist an actual engine result, never a model assertion of completion.',writes=True,identifier=P('string','operation id',True),result=P('object','worker result',True))
def operation_finish(rec,identifier,result):return execution.operation_finish(rec,identifier,result)
