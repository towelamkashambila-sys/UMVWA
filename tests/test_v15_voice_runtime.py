import os
from fastapi.testclient import TestClient
from app.main import app
from app.db import DB_PATH, init_db


def login(client, user, password):
    r=client.post('/api/auth/login',json={'username':user,'password':password})
    assert r.status_code==200
    return r.json()['token']


def test_voice_upload_and_transcription_boundary(tmp_path):
    old=DB_PATH.exists()
    # Existing test harness already resets DB through the suite fixtures; this test
    # only asserts the production API contract against the current app database.
    with TestClient(app) as client:
        token=login(client,'person_sarah','demo-sarah')
        headers={'Authorization':f'Bearer {token}','Content-Type':'audio/webm'}
        r=client.post('/api/voice-notes/upload?title=Runtime%20capture',headers=headers,content=b'RIFF-test-audio')
        assert r.status_code==200, r.text
        body=r.json()
        assert body['transcription_status']=='PENDING_PROVIDER'
        assert body['transcript'] is None
        status=client.get(f"/api/voice-notes/{body['id']}/transcription",headers={'Authorization':f'Bearer {token}'})
        assert status.status_code==200
        assert status.json()['status']=='PENDING_PROVIDER'
        audio=client.get(f"/api/voice-notes/{body['id']}/audio",headers={'Authorization':f'Bearer {token}'})
        assert audio.status_code==200
        assert audio.content==b'RIFF-test-audio'
