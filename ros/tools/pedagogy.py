"""Tools for advanced pedagogy bound to exact attempts and immutable item versions."""
from ..learn import pedagogy
from ..registry import tool, P

@tool('pedagogy_request', 'Request an explanation, tiered practice, raw-summary comparison, terms or bounded analogy without awarding mastery.', writes=True, lesson=P('string','saved lesson id',True), kind=P('string','teaching action',True,pedagogy.KINDS), item=P('string','immutable item hash'), attempt=P('string','exact saved attempt id'), text=P('string','raw summary or selected passage'), depth=P('string','explanation level',enum=pedagogy.DEPTHS), tier=P('integer','practice tier 1 to 3'), bloom=P('string','Bloom task level',enum=pedagogy.BLOOM), role=P('string','role for feedback'))
def request(rec,lesson,kind,item=None,attempt=None,text='',depth='intermediate',tier=1,bloom='understand',role='researcher'): return pedagogy.request(rec,lesson,kind,item,attempt,text,depth,tier,bloom,role)

@tool('pedagogy_reply', 'Save tutor feedback against the original request, item version and attempt without grading another answer.', writes=True, request=P('string','request event id',True), text=P('string','prepared response',True), by=P('string','tutor or provider',True))
def reply(rec,request,text,by): return pedagogy.reply(rec,request,text,by)

@tool('pedagogy_history', 'Read previous explanation variants and assistance with exact request and attempt attribution.', lesson=P('string','saved lesson id',True))
def history(rec,lesson): return pedagogy.history(rec,lesson)
