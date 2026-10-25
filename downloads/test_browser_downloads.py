import json
import os
import sys
from pathlib import Path
from urllib.request import Request

from web_common.downloads import browser_downloads
from web_common.downloads import downloader_handoff


def test_tracker_filters_download_state_by_browser(tmp_path, monkeypatch):
    sent_entries = []

    def fake_launch(entries, start_path):
        sent_entries.extend(entries)
        return True, ""

    monkeypatch.setattr(browser_downloads, "launch_downloader", fake_launch)
    state_path = tmp_path / "download_state.json"
    first = browser_downloads.BrowserDownloadTracker(
        tmp_path / "first.json", state_path
    )
    second = browser_downloads.BrowserDownloadTracker(
        tmp_path / "second.json", state_path
    )

    assert first.submit_url("https://example.test/a.zip", "browser.py")[0] == "sent"
    assert second.submit_url("https://example.test/b.zip", "browser.py")[0] == "sent"

    state_path.write_text(
        json.dumps(
            {
                "entries": [
                    {"id": entry["id"], "title": entry["title"], "status": "waiting"}
                    for entry in sent_entries
                ]
            }
        ),
        encoding="utf-8",
    )

    assert [item["id"] for item in first.get_entries()] == [sent_entries[0]["id"]]
    assert [item["id"] for item in second.get_entries()] == [sent_entries[1]["id"]]


def test_tracker_does_not_record_unsupported_urls(tmp_path, monkeypatch):
    def fail_if_called(*_args):
        raise AssertionError("Downloader must not receive unsupported URL")

    monkeypatch.setattr(browser_downloads, "launch_downloader", fail_if_called)
    tracker = browser_downloads.BrowserDownloadTracker(
        tmp_path / "browser.json", tmp_path / "state.json"
    )

    status, _message = tracker.submit_url("blob:https://example.test/id", "browser.py")

    assert status == "unsupported"
    assert not (tmp_path / "browser.json").exists()


def test_tracker_removes_id_when_handoff_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(
        browser_downloads,
        "launch_downloader",
        lambda *_args: (False, "Downloader unavailable"),
    )
    tracker = browser_downloads.BrowserDownloadTracker(
        tmp_path / "browser.json", tmp_path / "state.json"
    )

    status, message = tracker.submit_url("https://example.test/a.zip", "browser.py")

    assert status == "error"
    assert message == "Downloader unavailable"
    assert json.loads((tmp_path / "browser.json").read_text(encoding="utf-8"))["ids"] == []


def test_source_checkout_prefers_local_downloader_over_installed_executable(
    tmp_path, monkeypatch
):
    script = tmp_path / "Downloader" / "download_manager.py"
    script.parent.mkdir()
    script.write_text("", encoding="utf-8")
    start_path = tmp_path / "MiniBrowser" / "window.py"
    start_path.parent.mkdir()
    start_path.write_text("", encoding="utf-8")

    installed = tmp_path / "ProgramFiles" / "IARA" / "Downloader.exe"
    installed.parent.mkdir(parents=True)
    installed.write_text("", encoding="utf-8")
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "ProgramFiles"))

    launch = {}

    def fake_popen(command, cwd):
        launch["command"] = command
        launch["cwd"] = cwd

    monkeypatch.setattr(downloader_handoff.subprocess, "Popen", fake_popen)

    ok, error = downloader_handoff.launch_downloader(
        [{"url": "https://example.edu/file.pdf"}],
        str(start_path),
    )

    assert ok
    assert not error
    assert launch["command"][:2] == [sys.executable, str(script)]
    assert launch["cwd"] == str(script.parent)
    handoff_path = launch["command"][2]
    assert json.loads(Path(handoff_path).read_text(encoding="utf-8"))[0]["url"] == (
        "https://example.edu/file.pdf"
    )
    os.unlink(handoff_path)


def test_tracker_passes_only_cookies_matching_url(tmp_path, monkeypatch):
    sent_entries = []
    monkeypatch.setattr(
        browser_downloads,
        "launch_downloader",
        lambda entries, _start_path: (sent_entries.extend(entries) or True, ""),
    )
    tracker = browser_downloads.BrowserDownloadTracker(
        tmp_path / "browser.json", tmp_path / "state.json"
    )
    cookies = [
        {
            "name": "MoodleSession",
            "value": "secret",
            "domain": ".example.edu",
            "path": "/pluginfile.php",
            "secure": True,
        },
        {
            "name": "OtherSite",
            "value": "not-for-this-site",
            "domain": "other.example",
            "path": "/",
        },
    ]

    status, _message = tracker.submit_url(
        "https://moodle.example.edu/pluginfile.php/file.pdf",
        "browser.py",
        auth_cookies=cookies,
    )

    assert status == "sent"
    assert [
        cookie["name"] for cookie in sent_entries[0]["auth_cookies"]
    ] == ["MoodleSession"]
    tracking = json.loads((tmp_path / "browser.json").read_text(encoding="utf-8"))
    assert "secret" not in json.dumps(tracking)


def test_request_cookie_jar_preserves_cookie_scope_and_expiry():
    jar = browser_downloads.request_cookie_jar(
        [
            {
                "name": "sid",
                "value": "secret",
                "domain": "moodle.example.edu",
                "path": "/pluginfile.php",
                "secure": True,
            },
            {
                "name": "expired",
                "value": "old",
                "domain": "moodle.example.edu",
                "path": "/",
                "expires_at": 1,
            },
        ],
        "https://moodle.example.edu/pluginfile.php/course/file.pdf",
    )

    request = Request("https://moodle.example.edu/pluginfile.php/course/file.pdf")
    jar.add_cookie_header(request)
    assert request.get_header("Cookie") == "sid=secret"
    redirected = Request("https://unrelated.example/file.pdf")
    jar.add_cookie_header(redirected)
    assert redirected.get_header("Cookie") is None


def test_host_only_cookie_does_not_cross_to_subdomain():
    cookies = [
        {
            "name": "sid",
            "value": "secret",
            "domain": "moodle.example.edu",
            "path": "/",
        }
    ]

    assert browser_downloads.cookies_for_url(
        cookies, "https://moodle.example.edu/file.pdf"
    )
    assert not browser_downloads.cookies_for_url(
        cookies, "https://sub.moodle.example.edu/file.pdf"
    )


def test_browser_download_headers_keep_profile_user_agent_and_referer():
    cookie_store = browser_downloads.BrowserCookieStore.__new__(
        browser_downloads.BrowserCookieStore
    )

    class Profile:
        def httpUserAgent(self):
            return "Mozilla/5.0 (X11; Linux x86_64) Chrome/131"

    cookie_store.profile = Profile()

    assert cookie_store.headers_for_download("https://moodle.example.edu/course") == {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/131",
        "Referer": "https://moodle.example.edu/course",
    }


def test_status_formatter_shows_downloader_progress():
    label = browser_downloads.format_downloader_entry(
        {"title": "Archive", "status": "downloading", "progress": 42, "speed_text": "1 MB/s"}
    )

    assert label == "Archive — Descargando (42%) — 1 MB/s"


def test_status_formatter_distinguishes_archive_extraction():
    label = browser_downloads.format_downloader_entry(
        {
            "title": "Archive",
            "status": "finished",
            "extract_status": "running",
        }
    )

    assert "Extrayendo" in label
