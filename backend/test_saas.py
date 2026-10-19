"""Auth, tenant-boundary, email, migration and research regression tests."""
import hashlib, sqlite3, time
import pytest
from fastapi.testclient import TestClient
import backend.main as m

@pytest.fixture
def env(monkeypatch,tmp_path):
    for key in ('DATABASE_URL','VERCEL','SETUP_TOKEN','SMTP_HOST','SMTP_FROM','PUBLIC_ORIGIN','TAVILY_API_KEY','LLM_API_KEY','LLM_BASE_URL','LLM_MODEL'):
        monkeypatch.delenv(key,raising=False)
    monkeypatch.setenv('REQUIRE_EMAIL_VERIFICATION','false')
    monkeypatch.setenv('COOKIE_SECURE','false')
    monkeypatch.setattr(m,'DB',str(tmp_path/'saas.db'))
    monkeypatch.setattr(m,'_initialized',False)
    return monkeypatch

def register(client,email='alice@example.com'):
    r=client.post('/api/register',json={'name':'Test owner','email':email,'password':'long-password-test'})
    assert r.status_code==200,r.text
    return r

def test_pages_and_api_require_session(env):
    c=TestClient(m.app)
    for path in ('/','/app','/agent','/create','/overview','/connections','/profile','/app/','/index.html','/app/index.html'):
        r=c.get(path,follow_redirects=False)
        assert r.status_code==303 and r.headers['location']=='/login',path
    for path in ('/login','/register','/forgot-password','/reset-password','/verify-email','/join','/style.css','/app.js','/auth.js'):
        assert c.get(path).status_code==200,path
    assert c.get('/api/state').status_code==401
    assert c.get('/api/audit').status_code==401
    assert c.post('/api/agents',json={'name':'X','role':'X','instructions':'X'}).status_code==401
    register(c)
    assert c.get('/app').status_code==200
    c.post('/api/logout',json={})
    assert c.get('/app',follow_redirects=False).status_code==303
    assert c.get('/api/state').status_code==401

def test_workspace_isolation_all_surfaces(env):
    a,b=TestClient(m.app),TestClient(m.app)
    register(a);register(b,'bob@example.com')
    sa,sb=a.get('/api/state').json(),b.get('/api/state').json()
    assert sa['workspace_id']!=sb['workspace_id']
    assert {x['id'] for x in sa['agents']}.isdisjoint(x['id'] for x in sb['agents'])
    assert [u['email'] for u in sb['users']]==['bob@example.com']
    target=sa['agents'][0];aid=target['id']
    assert b.put('/api/agents/'+aid,json=target).status_code==404
    assert b.post('/api/agents/'+aid+'/messages',json={'content':'Steal'}).status_code==404
    assert b.post('/api/agents/'+aid+'/research',json={'content':'Steal','confirmed':True}).status_code==404
    assert b.post('/api/invites',json={'email':'x@example.com','grants':[{'agent_id':aid,'permission':'operator'}]}).status_code==404
    new={'name':'Evil','role':'Test','instructions':'Test','reports_to':aid}
    assert b.post('/api/agents',json=new).status_code==422
    own=sb['agents'][0];own['reports_to']=aid
    assert b.put('/api/agents/'+own['id'],json=own).status_code==422
    inv=a.post('/api/invites',json={'email':'member@example.com','grants':[{'agent_id':aid,'permission':'viewer'}]}).json()
    member=TestClient(m.app)
    r=member.post('/api/invites/accept',json={'name':'Member','email':'member@example.com','password':'long-password-test','token':inv['token']})
    assert r.status_code==200
    ms=member.get('/api/state').json();uid=ms['me']['id']
    assert ms['workspace_id']==sa['workspace_id'] and len(ms['agents'])==1
    assert b.put('/api/users/'+uid+'/grants',json={'grants':[]}).status_code==400
    async def generate(*args):return 'Private draft for Alice'
    env.setattr(m,'generate',generate)
    assert a.post('/api/agents/'+aid+'/messages',json={'content':'Private request'}).status_code==200
    task=a.get('/api/state').json()['tasks'][0]
    assert b.post('/api/tasks/'+task['id']+'/decision',json={'status':'approved'}).status_code==404
    assert member.post('/api/tasks/'+task['id']+'/decision',json={'status':'approved'}).status_code==403
    assert b.get('/api/state').json()['tasks']==[] and b.get('/api/state').json()['messages']==[]
    assert all(row['user_id']==sb['me']['id'] for row in b.get('/api/audit').json())
    assert a.put('/api/users/'+uid+'/grants',json={'grants':[]}).status_code==200
    assert member.get('/api/state').json()['agents']==[]

def test_verification_gate_and_single_use(env):
    env.setenv('REQUIRE_EMAIL_VERIFICATION','true')
    c=TestClient(m.app)
    assert c.post('/api/register',json={'name':'A','email':'alice@example.com','password':'long-password-test'}).status_code==503
    env.setenv('SMTP_HOST','smtp.test');env.setenv('SMTP_FROM','hello@example.com');env.setenv('PUBLIC_ORIGIN','https://bainbot.example')
    mails=[]
    env.setattr(m,'send_email',lambda *args:mails.append(args))
    assert register(c).json()['verification_required']
    assert c.get('/api/state').status_code==401
    assert c.post('/api/login',json={'email':'alice@example.com','password':'long-password-test'}).status_code==403
    first=mails[-1][2].split('?token=')[1]
    assert c.post('/api/resend-verification',json={'email':'alice@example.com'}).status_code==200
    token=mails[-1][2].split('?token=')[1]
    assert first!=token
    assert c.post('/api/verify-email',json={'token':first}).status_code==400
    assert c.post('/api/verify-email',json={'token':token}).status_code==200
    assert c.post('/api/verify-email',json={'token':token}).status_code==400
    assert c.post('/api/login',json={'email':'alice@example.com','password':'long-password-test'}).status_code==200
    assert c.get('/api/state').status_code==200

def test_mail_failure_rolls_back_registration(env):
    from fastapi import HTTPException
    env.setenv('REQUIRE_EMAIL_VERIFICATION','true');env.setenv('SMTP_HOST','smtp.test');env.setenv('SMTP_FROM','hello@example.com');env.setenv('PUBLIC_ORIGIN','https://bainbot.example')
    def fail(*args):raise HTTPException(503,'Mail failed')
    env.setattr(m,'send_email',fail)
    c=TestClient(m.app)
    assert c.post('/api/register',json={'name':'A','email':'alice@example.com','password':'long-password-test'}).status_code==503
    with m.connect() as db:assert not db.execute('SELECT 1 FROM users').fetchone()

def test_research_permissions_and_results(env):
    import backend.search as search
    env.setenv('TAVILY_API_KEY','test-only-key')
    payloads=[]
    class Result:
        def raise_for_status(self):pass
        def json(self):return {'answer':'Research summary','results':[{'title':'Source','url':'https://example.com/report','content':'Useful information'},{'title':'Bad','url':'javascript:alert(1)','content':'bad'}]}
    class HTTP:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,**kwargs):payloads.append((url,kwargs));return Result()
    env.setattr(search.httpx,'AsyncClient',HTTP)
    c=TestClient(m.app);register(c)
    agent=c.get('/api/state').json()['agents'][0];url='/api/agents/'+agent['id']+'/research'
    assert c.post(url,json={'content':'A research question'}).status_code==409
    assert not payloads
    assert c.post(url,json={'content':'A research question','confirmed':True}).status_code==200
    state=c.get('/api/state').json();assert state['tasks'][0]['status']=='completed'
    assert 'https://example.com/report' in state['messages'][-1]['content']
    assert 'javascript:' not in state['messages'][-1]['content']
    assert payloads[0][0]=='https://api.tavily.com/search'
    assert payloads[0][1]['headers']['Authorization']=='Bearer test-only-key'
    agent['action_permissions']={'research':'block'}
    assert c.put('/api/agents/'+agent['id'],json=agent).status_code==200
    assert c.post(url,json={'content':'A question','confirmed':True}).status_code==403
    assert len(payloads)==1

def test_workspace_usage_limit(env):
    env.setenv('FREE_DAILY_DRAFTS','1')
    async def generate(*args):return 'Draft'
    env.setattr(m,'generate',generate)
    c=TestClient(m.app);register(c);aid=c.get('/api/state').json()['agents'][0]['id']
    assert c.post('/api/agents/'+aid+'/messages',json={'content':'One'}).status_code==200
    assert c.post('/api/agents/'+aid+'/messages',json={'content':'Two'}).status_code==429

def test_migration_preserves_legacy_data(env):
    c=sqlite3.connect(m.DB)
    c.executescript("CREATE TABLE users(id TEXT PRIMARY KEY,name TEXT,email TEXT UNIQUE,password TEXT,role TEXT); CREATE TABLE agents(id TEXT PRIMARY KEY,name TEXT,role TEXT,instructions TEXT,model TEXT,status TEXT,avatar INTEGER);")
    c.execute('INSERT INTO users VALUES(?,?,?,?,?)',('old','Owner','legacy@example.com',m.password('old-password-test'),'owner'))
    c.execute('INSERT INTO agents VALUES(?,?,?,?,?,?,?)',('1','Legacy agent','Test','Test','','active',0));c.commit();c.close()
    m.init();m.init()
    client=TestClient(m.app)
    assert client.post('/api/login',json={'email':'legacy@example.com','password':'old-password-test'}).status_code==200
    state=client.get('/api/state').json();assert state['workspace_id']=='legacy' and state['agents'][0]['id']=='1'
    other=TestClient(m.app);register(other)
    assert all(a['id']!='1' for a in other.get('/api/state').json()['agents'])

def test_validation_and_expired_session(env):
    c=TestClient(m.app)
    assert c.post('/api/register',json={'name':'A','email':'invalid','password':'long-password-test'}).status_code==422
    register(c)
    with m.connect() as db:db.execute('UPDATE sessions SET expires=?',(time.time()-1,))
    assert c.get('/api/state').status_code==401
    assert c.get('/overview',follow_redirects=False).status_code==303
