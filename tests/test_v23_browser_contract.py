from pathlib import Path


def test_settings_frontend_notification_control_matches_select_semantics():
    html = Path('app/index.html').read_text()
    assert "notifications:document.getElementById('prefNotify').value==='true'" in html
    assert "<select id=\"prefNotify\"><option value=\"true\"" in html
    assert "<option value=\"false\"" in html
