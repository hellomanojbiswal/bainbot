import os,tempfile
os.environ['BAINBOT_DB']=tempfile.mktemp(suffix='.sqlite3')
from fastapi.testclient import TestClient
from backend.main import app

def test_end_to_end_access_and_persistence():
    owner=TestClient(app);viewer=TestClient(app);anonymous=TestClient(app)
    assert anonymous.get('/api/state').status_code==401
    assert owner.post('/api/setup',json={'name':'Owner','email':'owner@test.local','password':'long-test-password'}).status_code==200
    assert owner.post('/api/setup',json={'email':'x@test.local','password':'long-test-password'}).status_code==409
    s=owner.get('/api/state').json();aid=s['agents'][0]['id'];other=s['agents'][1]['id']
    inv=owner.post('/api/invites',json={'email':'viewer@test.local','grants':[{'agent_id':aid,'permission':'viewer'}]}).json()
    assert viewer.post('/api/invites/accept',json={'name':'Viewer','email':'viewer@test.local','password':'viewer-test-password','token':inv['token']}).status_code==200
    vs=viewer.get('/api/state').json();assert len(vs['agents'])==1 and vs['agents'][0]['id']==aid
    assert viewer.post('/api/agents/'+aid+'/messages',json={'content':'Hello'}).status_code==403
    assert viewer.post('/api/agents/'+other+'/messages',json={'content':'Hello'}).status_code==403
    assert viewer.post('/api/agents',json={'name':'Unauthorized','role':'test','instructions':'test'}).status_code==403
    uid=vs['me']['id']
    assert owner.put('/api/users/'+uid+'/grants',json={'grants':[{'agent_id':aid,'permission':'operator'}]}).status_code==200
    assert viewer.post('/api/agents/'+aid+'/messages',json={'content':'Hello'}).status_code==503
    assert owner.put('/api/users/'+uid+'/grants',json={'grants':[]}).status_code==200
    assert viewer.get('/api/state').json()['agents']==[]
    assert owner.post('/api/agents',json={'name':'Test Agent','role':'Research','instructions':'Draft reports'}).status_code==200
    assert len(owner.get('/api/state').json()['agents'])==6
    assert owner.post('/api/logout',json={}).status_code==200
    assert owner.get('/api/state').status_code==401
    assert owner.post('/api/login',json={'email':'owner@test.local','password':'long-test-password'}).status_code==200
    assert len(owner.get('/api/state').json()['agents'])==6
    assert owner.put('/api/profile',json={'name':'Changed'},headers={'Origin':'https://evil.example'}).status_code==403

def test_approval_and_mock_provider(monkeypatch):
    import backend.main as m
    owner=TestClient(app);owner.post('/api/login',json={'email':'owner@test.local','password':'long-test-password'})
    class Result:
        def raise_for_status(self):pass
        def json(self):return {'choices':[{'message':{'content':'A useful draft'}}]}
    class Client:
        def __init__(self,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,*args,**kw):return Result()
    monkeypatch.setenv('LLM_API_KEY','test');monkeypatch.setenv('LLM_BASE_URL','https://test.invalid/v1');monkeypatch.setenv('LLM_MODEL','test-model');monkeypatch.setattr(m.httpx,'AsyncClient',Client)
    assert owner.post('/api/agents/1/messages',json={'content':'Draft a plan'}).status_code==200
    t=owner.get('/api/state').json()['tasks'][0]
    r=owner.post('/api/tasks/'+t['id']+'/decision',json={'status':'approved'})
    assert r.status_code==200 and r.json()['external_action'] is False
    assert owner.post('/api/tasks/'+t['id']+'/decision',json={'status':'approved'}).status_code==409

def test_reporting_and_execution_modes(monkeypatch,tmp_path):
    import backend.main as m
    monkeypatch.setattr(m,'DB',str(tmp_path/'settings.db'));m.init()
    client=TestClient(app)
    assert client.post('/api/setup',json={'email':'settings@test.local','password':'settings-test-password'}).status_code==200
    agents=client.get('/api/state').json()['agents']
    a,b=agents[:2]
    assert a['approval_mode']=='approval' and a['reports_to']=='owner'
    a.update(reports_to=b['id'],approval_mode='direct')
    assert client.put('/api/agents/'+a['id'],json=a).status_code==200
    b['reports_to']=a['id']
    assert client.put('/api/agents/'+b['id'],json=b).status_code==422
    a['reports_to']=a['id']
    assert client.put('/api/agents/'+a['id'],json=a).status_code==422
    a['reports_to']='nonexistent'
    assert client.put('/api/agents/'+a['id'],json=a).status_code==422
    saved=client.get('/api/state').json()['agents'][0]
    assert saved['reports_to']==b['id'] and saved['approval_mode']=='direct'
    class Result:
        def raise_for_status(self):pass
        def json(self):return {'choices':[{'message':{'content':'Draft only'}}]}
    class Client:
        def __init__(self,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,*args,**kw):return Result()
    monkeypatch.setattr(m.httpx,'AsyncClient',Client)
    monkeypatch.setenv('LLM_API_KEY','test');monkeypatch.setenv('LLM_BASE_URL','https://test.invalid/v1');monkeypatch.setenv('LLM_MODEL','test')
    assert client.post('/api/agents/'+a['id']+'/messages',json={'content':'Draft a plan'}).status_code==200
    task=client.get('/api/state').json()['tasks'][0]
    assert task['status']=='ready'
    assert client.post('/api/tasks/'+task['id']+'/decision',json={'status':'approved'}).status_code==409
    saved['approval_mode']='approval'
    assert client.put('/api/agents/'+a['id'],json=saved).status_code==200
    assert client.post('/api/agents/'+a['id']+'/messages',json={'content':'Draft another plan'}).status_code==200
    tasks=client.get('/api/state').json()['tasks']
    assert tasks[0]['status']=='pending' and tasks[1]['status']=='ready'

def test_action_permissions_persist_and_enforce(monkeypatch,tmp_path):
    import backend.main as m
    monkeypatch.setattr(m,'DB',str(tmp_path/'policies.db'));m.init()
    client=TestClient(app)
    client.post('/api/setup',json={'email':'policies@test.local','password':'policies-test-password'})
    a=client.get('/api/state').json()['agents'][0]
    a.update(approval_mode='direct',action_permissions={'draft':'block','email':'approval','research':'allow'})
    assert client.put('/api/agents/'+a['id'],json=a).status_code==200
    saved=client.get('/api/state').json()['agents'][0]
    assert saved['action_permissions']==a['action_permissions']
    assert client.post('/api/agents/'+a['id']+'/messages',json={'content':'Write a draft'}).status_code==403
    assert m.action_policy(saved,'email')=='approval'
    assert m.action_policy(saved,'research')=='allow'
    saved['approval_mode']='approval'
    assert m.action_policy(saved,'research')=='approval'
    assert m.action_policy(saved,'draft')=='block'
    saved['action_permissions']={'unsupported':'allow'}
    assert client.put('/api/agents/'+a['id'],json=saved).status_code==422
