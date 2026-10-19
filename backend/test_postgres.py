"""Runs against an explicitly designated, empty test database only."""
import os,secrets
import pytest
from fastapi.testclient import TestClient
import backend.main as m
@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'),reason='No PostgreSQL test database configured')
def test_postgres_full_flow(monkeypatch):
    monkeypatch.setenv('DATABASE_URL',os.environ['TEST_DATABASE_URL'])
    monkeypatch.delenv('SETUP_TOKEN',raising=False)
    m.init();client=TestClient(m.app)
    email='owner-'+secrets.token_hex(4)+'@example.com'
    assert client.post('/api/setup',json={'email':email,'password':'postgres-test-password'}).status_code==200
    state=client.get('/api/state').json();a=state['agents'][0]
    a['reports_to']='owner'
    assert client.put('/api/agents/'+a['id'],json=a).status_code==200
    invitation=client.post('/api/invites',json={'email':'member@example.com','grants':[{'agent_id':a['id'],'permission':'viewer'}]}).json()
    member=TestClient(m.app)
    assert member.post('/api/invites/accept',json={'email':'member@example.com','password':'member-test-password','token':invitation['token']}).status_code==200
    uid=member.get('/api/state').json()['me']['id']
    assert client.put('/api/users/'+uid+'/grants',json={'grants':[{'agent_id':a['id'],'permission':'operator'}]}).status_code==200
    async def generate(*args):return 'Postgres-backed model draft'
    monkeypatch.setattr(m,'generate',generate)
    assert client.post('/api/agents/'+a['id']+'/messages',json={'content':'Draft'}).status_code==200
    task=client.get('/api/state').json()['tasks'][0]
    assert client.post('/api/tasks/'+task['id']+'/decision',json={'status':'approved'}).status_code==200
    assert client.get('/api/health').json()['database']=='postgresql'

@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'),reason='No PostgreSQL test database configured')
def test_postgres_workspace_isolation(monkeypatch):
    monkeypatch.setenv('DATABASE_URL',os.environ['TEST_DATABASE_URL'])
    monkeypatch.setenv('REQUIRE_EMAIL_VERIFICATION','false')
    m.init()
    a,b=TestClient(m.app),TestClient(m.app)
    for client in (a,b):
        email='workspace-'+secrets.token_hex(8)+'@example.com'
        assert client.post('/api/register',json={'name':'Test owner','email':email,'password':'postgres-test-password'}).status_code==200
    sa,sb=a.get('/api/state').json(),b.get('/api/state').json()
    assert sa['workspace_id']!=sb['workspace_id']
    assert len(sb['users'])==1
    assert b.put('/api/agents/'+sa['agents'][0]['id'],json=sa['agents'][0]).status_code==404
    assert b.post('/api/agents/'+sa['agents'][0]['id']+'/messages',json={'content':'Forbidden'}).status_code==404
