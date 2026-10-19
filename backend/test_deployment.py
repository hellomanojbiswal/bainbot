import hashlib,time
import pytest
from fastapi.testclient import TestClient
import backend.main as m

@pytest.fixture
def client(monkeypatch,tmp_path):
    monkeypatch.delenv('DATABASE_URL',raising=False)
    monkeypatch.delenv('VERCEL',raising=False)
    monkeypatch.delenv('SETUP_TOKEN',raising=False)
    monkeypatch.setattr(m,'DB',str(tmp_path/'test.db'));m.init()
    return TestClient(m.app)

def setup(client,**extra):
    return client.post('/api/setup',json={'name':'Owner','email':'owner@example.com','password':'password-for-testing',**extra})

def test_setup_token_and_clean_pages(client,monkeypatch):
    monkeypatch.setenv('SETUP_TOKEN','private-test-code')
    assert setup(client).status_code==403
    assert setup(client,setup_token='private-test-code').status_code==200
    for path in ['/','/login','/register','/forgot-password','/reset-password','/app.js','/auth.js','/assets/mascots.webp']:
        assert client.get(path).status_code==200,path
    assert client.get('/api/health').json()['database']=='sqlite'
    assert setup(client,setup_token='private-test-code').status_code==409

def test_reset_one_use_invalidates_sessions(client,monkeypatch):
    setup(client)
    monkeypatch.setenv('SMTP_FROM','hello@example.com');monkeypatch.setenv('SMTP_HOST','smtp.invalid');monkeypatch.setenv('PUBLIC_ORIGIN','https://bainbot.example')
    mails=[]
    class SMTP:
        def __init__(self,*a,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def starttls(self):pass
        def login(self,*a):pass
        def send_message(self,msg):mails.append(msg)
    monkeypatch.setattr(m.smtplib,'SMTP',SMTP)
    assert client.post('/api/forgot-password',json={'email':'owner@example.com'}).status_code==200
    token=mails[0].get_content().split('?token=')[1].split()[0]
    r=client.post('/api/reset-password',json={'token':token,'password':'new-password-for-testing'})
    assert r.status_code==200
    assert client.get('/api/state').status_code==401
    assert client.post('/api/reset-password',json={'token':token,'password':'new-password-for-testing'}).status_code==400
    assert client.post('/api/login',json={'email':'owner@example.com','password':'new-password-for-testing'}).status_code==200

def test_pause_during_provider_request(client,monkeypatch):
    setup(client)
    async def generate(*args):
        with m.connect() as c:c.execute("UPDATE agents SET status='paused' WHERE id='1'")
        return 'A draft'
    monkeypatch.setattr(m,'generate',generate)
    assert client.post('/api/agents/1/messages',json={'content':'Please draft'}).status_code==409
    assert client.get('/api/state').json()['tasks']==[]

def test_error_does_not_make_task(client,monkeypatch):
    from fastapi import HTTPException
    setup(client)
    async def generate(*args):raise HTTPException(502,'Provider error')
    monkeypatch.setattr(m,'generate',generate)
    assert client.post('/api/agents/1/messages',json={'content':'Draft'}).status_code==502
    assert client.get('/api/state').json()['messages']==[]

def test_rate_limits_persist(client):
    for _ in range(10):assert client.post('/api/login',json={'email':'none@example.com','password':'wrong'}).status_code==401
    assert client.post('/api/login',json={'email':'none@example.com','password':'wrong'}).status_code==429

def test_expired_reset(client):
    setup(client)
    with m.connect() as c:
        uid=c.execute('SELECT id FROM users').fetchone()['id']
        c.execute('INSERT INTO resets VALUES(?,?,?)',(hashlib.sha256(b'expired-reset-token-long').hexdigest(),uid,time.time()-1))
    assert client.post('/api/reset-password',json={'token':'expired-reset-token-long','password':'new-password-for-testing'}).status_code==400
