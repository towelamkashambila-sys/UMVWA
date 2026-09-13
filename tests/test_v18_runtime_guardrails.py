from fastapi.testclient import TestClient
from app.main import app


def login(client, username='person_david', password='demo-david'):
    r=client.post('/api/auth/login',json={'username':username,'password':password})
    assert r.status_code==200
    return r.json()['token']


def test_health_and_readiness_are_live():
    with TestClient(app) as c:
        assert c.get('/api/health').json()['persistence']=='reachable'
        assert c.get('/api/ready').status_code==200


def test_security_headers_and_request_id():
    with TestClient(app) as c:
        r=c.get('/api/health',headers={'x-request-id':'test-request-18'})
        assert r.headers['X-Request-ID']=='test-request-18'
        assert r.headers['X-Content-Type-Options']=='nosniff'
        assert r.headers['X-Frame-Options']=='DENY'
        assert r.headers['Cache-Control']=='no-store'


def test_authenticated_session_still_works_under_runtime_guardrails():
    with TestClient(app) as c:
        token=login(c)
        r=c.get('/api/auth/session',headers={'Authorization':'Bearer '+token})
        assert r.status_code==200
        assert r.json()['role']=='EXECUTIVE'
