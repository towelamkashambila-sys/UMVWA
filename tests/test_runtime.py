import os, tempfile
from pathlib import Path
os.environ['PYTHONPATH']=str(Path(__file__).resolve().parents[1]) + ':' + str(Path(__file__).resolve().parents[1]/'canonical_src')

def test_canonical_package_imports():
    from alignai.canonical.models import WorkItem, Evidence
    from alignai.canonical.enums import LifecycleState
    assert WorkItem and Evidence and LifecycleState

def test_runtime_app_imports():
    from app.main import app
    assert app.title == 'UMVWA'
