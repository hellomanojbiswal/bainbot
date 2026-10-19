"""Provider contracts and single-prompt workflow tests. No live credentials used."""
import asyncio,json
import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException
import backend.main as m
import backend.workflow as w
import backend.search as search
import backend.provider as provider

@pytest.fixture
def client(monkeypatch,tmp_path):
    for key in ('DATABASE_URL','VERCEL','SMTP_HOST','SMTP_FROM','EMAIL_FROM','RESEND_API_KEY','EMAIL_TEST_RECIPIENT','TINYFISH_API_KEY','TAVILY_API_KEY','SEARCH_PROVIDER','PUBLIC_ORIGIN','LLM_OUTPUT_LIMIT'):
        monkeypatch.delenv(key,raising=False)
    monkeypatch.setenv('REQUIRE_EMAIL_VERIFICATION','false');monkeypatch.setenv('COOKIE_SECURE','false')
    monkeypatch.setattr(m,'DB',str(tmp_path/'providers.db'));monkeypatch.setattr(m,'_initialized',False)
    c=TestClient(m.app)
    assert c.post('/api/register',json={'name':'Owner','email':'owner@example.com','password':'long-password-test'}).status_code==200
    for key,value in [('LLM_BASE_URL','https://openrouter.ai/api/v1'),('LLM_MODEL','openrouter/free'),('LLM_API_KEY','test-only-model-key')]:monkeypatch.setenv(key,value)
    return c

def agent(client):return client.get('/api/state').json()['agents'][0]
def tool_call(name='search_web',query='Market trends'):
    return {'role':'assistant','content':None,'tool_calls':[{'id':'call_1','type':'function','function':{'name':name,'arguments':json.dumps({'query':query})}}]}

def test_openrouter_wire_contract(client,monkeypatch):
    seen=[]
    class R:
        def raise_for_status(self):pass
        def json(self):return {'choices':[{'message':{'content':'A useful response'}}]}
    class HTTP:
        def __init__(self,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def post(self,url,**kw):seen.append((url,kw));return R()
    monkeypatch.setattr(provider.httpx,'AsyncClient',HTTP)
    assert asyncio.run(provider.generate([{'role':'user','content':'Hello'}]))=='A useful response'
    assert seen[0][0]=='https://openrouter.ai/api/v1/chat/completions'
    assert seen[0][1]['json']['model']=='openrouter/free'
    assert seen[0][1]['headers']['Authorization']=='Bearer test-only-model-key'

def test_tinyfish_wire_contract(client,monkeypatch):
    seen=[];monkeypatch.setenv('SEARCH_PROVIDER','tinyfish');monkeypatch.setenv('TINYFISH_API_KEY','test-only-search-key')
    class R:
        def raise_for_status(self):pass
        def json(self):return {'results':[{'title':'Report','snippet':'Evidence','url':'https://example.com/report'}]}
    class HTTP:
        def __init__(self,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def get(self,url,**kw):seen.append((url,kw));return R()
    monkeypatch.setattr(search.httpx,'AsyncClient',HTTP)
    text=asyncio.run(search.search_web('Market trends'))
    assert 'Evidence' in text and 'https://example.com/report' in text
    assert seen[0][0]=='https://api.search.tinyfish.ai'
    assert seen[0][1]['params']=={'query':'Market trends'}
    assert seen[0][1]['headers']=={'X-API-Key':'test-only-search-key'}

def test_resend_registration_verify_and_reset(client,monkeypatch):
    monkeypatch.setenv('REQUIRE_EMAIL_VERIFICATION','true');monkeypatch.setenv('RESEND_API_KEY','test-only-mail-key')
    monkeypatch.setenv('EMAIL_FROM','Bainbot <onboarding@resend.dev>');monkeypatch.setenv('EMAIL_TEST_RECIPIENT','new@example.com');monkeypatch.setenv('PUBLIC_ORIGIN','https://app.example.com')
    mails=[]
    class R:
        def raise_for_status(self):pass
        def json(self):return {'id':'email-test-id'}
    class HTTP:
        def __init__(self,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def post(self,url,**kw):mails.append((url,kw));return R()
    monkeypatch.setattr(m.httpx,'Client',HTTP)
    c=TestClient(m.app)
    assert c.post('/api/register',json={'name':'New','email':'new@example.com','password':'long-password-test'}).status_code==200
    assert c.get('/api/state').status_code==401
    assert mails[0][0]=='https://api.resend.com/emails'
    assert mails[0][1]['json']['to']==['new@example.com']
    assert mails[0][1]['headers']['Authorization']=='Bearer test-only-mail-key'
    token=mails[0][1]['json']['text'].split('?token=')[1]
    assert c.post('/api/verify-email',json={'token':token}).status_code==200
    assert c.post('/api/login',json={'email':'new@example.com','password':'long-password-test'}).status_code==200
    assert c.post('/api/forgot-password',json={'email':'new@example.com'}).status_code==200
    token=mails[-1][1]['json']['text'].split('?token=')[1].split()[0]
    assert c.post('/api/reset-password',json={'token':token,'password':'changed-password-test'}).status_code==200
    assert c.get('/api/state').status_code==401
    assert c.post('/api/register',json={'name':'Other','email':'other@example.com','password':'long-password-test'}).status_code==403
    assert len(mails)==2
    with m.connect() as db:assert not db.execute('SELECT id FROM users WHERE email=?',('other@example.com',)).fetchone()

def test_workflow_research_then_draft(client,monkeypatch):
    monkeypatch.setenv('TAVILY_API_KEY','test-only-search-key')
    replies=[tool_call(),{'content':'A grounded LinkedIn draft'}];seen=[]
    async def complete(history,*args,**kwargs):seen.append((list(history),kwargs));return replies.pop(0)
    async def research(query):assert query=='Market trends';return 'Source evidence\nhttps://example.com/report'
    monkeypatch.setattr(w,'complete',complete);monkeypatch.setattr(search,'search_web',research)
    url='/api/agents/'+agent(client)['id']+'/workflow'
    assert client.post(url,json={'content':'Research and draft a post'}).status_code==409
    assert not seen
    r=client.post(url,json={'content':'Research and draft a post','confirmed':True})
    assert r.status_code==200,r.text
    state=client.get('/api/state').json()
    assert state['tasks'][0]['status']=='pending'
    assert 'A grounded LinkedIn draft' in state['messages'][-1]['content']
    assert 'https://example.com/report' in state['messages'][-1]['content']
    assert seen[1][0][-1]['role']=='tool'
    assert r.json()['external_action'] is False

def test_workflow_denies_unknown_tools(client,monkeypatch):
    monkeypatch.setenv('TAVILY_API_KEY','test-only-search-key')
    async def complete(*args,**kwargs):return tool_call('send_email')
    monkeypatch.setattr(w,'complete',complete)
    r=client.post('/api/agents/'+agent(client)['id']+'/workflow',json={'content':'Send mail','confirmed':True})
    assert r.status_code==502
    state=client.get('/api/state').json();assert state['tasks'][0]['status']=='failed' and not state['messages']

def test_workflow_scope_and_research_block(client,monkeypatch):
    a=agent(client);a['action_permissions']={'research':'block'};client.put('/api/agents/'+a['id'],json=a)
    async def complete(history,*args,**kw):assert kw['tools'] is None;return {'content':'Draft from supplied facts'}
    monkeypatch.setattr(w,'complete',complete)
    assert client.post('/api/agents/'+a['id']+'/workflow',json={'content':'Write from my notes'}).status_code==200
    other=TestClient(m.app);other.post('/api/register',json={'name':'Other','email':'other@example.com','password':'long-password-test'})
    assert other.post('/api/agents/'+a['id']+'/workflow',json={'content':'Private data'}).status_code==404

def test_workflow_revoked_before_search(client,monkeypatch):
    monkeypatch.setenv('TAVILY_API_KEY','test-only-search-key');a=agent(client)
    async def complete(*args,**kw):
        with m.connect() as db:db.execute('UPDATE agents SET action_permissions=? WHERE id=?',(json.dumps({'research':'block'}),a['id']))
        return tool_call()
    async def research(*args):raise AssertionError('Search must not run')
    monkeypatch.setattr(w,'complete',complete);monkeypatch.setattr(search,'search_web',research)
    assert client.post('/api/agents/'+a['id']+'/workflow',json={'content':'Research','confirmed':True}).status_code==403
    assert client.get('/api/state').json()['tasks'][0]['status']=='failed'

def test_resend_errors_sanitized(client,monkeypatch):
    import httpx
    monkeypatch.setenv('RESEND_API_KEY','test-only-mail-key');monkeypatch.setenv('EMAIL_FROM','hello@example.com');monkeypatch.setenv('PUBLIC_ORIGIN','https://app.example.com')
    class HTTP:
        def __init__(self,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def post(self,*a,**kw):raise RuntimeError('Private upstream response')
    monkeypatch.setattr(m.httpx,'Client',HTTP)
    with pytest.raises(HTTPException) as err:m.send_email('owner@example.com','Verify','Token')
    assert 'Private' not in err.value.detail and err.value.status_code==503
