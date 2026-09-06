from pathlib import Path

from PyQt6.QtCore import QByteArray
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInterceptor


DEFAULT_SITE_USER_AGENTS = {
    "web.whatsapp.com": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}


class SiteUserAgentInterceptor(QWebEngineUrlRequestInterceptor):
    """Aplica User-Agent alternativos sólo a los sitios configurados."""

    def __init__(self, site_user_agents, parent=None):
        super().__init__(parent)
        self._site_user_agents = {
            host.lower().strip().strip("."): user_agent
            for host, user_agent in site_user_agents.items()
            if host and host.strip().strip(".")
        }

    def interceptRequest(self, info):
        host = info.requestUrl().host().lower().rstrip(".")
        for site, user_agent in self._site_user_agents.items():
            if host == site or host.endswith(f".{site}"):
                info.setHttpHeader(
                    QByteArray(b"User-Agent"),
                    QByteArray(user_agent.encode("ascii")),
                )
                break


def build_web_profile(
    name,
    parent,
    storage_path,
    cache_path=None,
    download_path=None,
    extra_settings=None,
    site_user_agents=None,
):
    storage = Path(storage_path)
    cache = Path(cache_path) if cache_path else storage / "cache"
    storage.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)

    profile = QWebEngineProfile(str(name), parent)
    profile.setPersistentStoragePath(str(storage))
    profile.setCachePath(str(cache))
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
    )
    user_agents = (
        DEFAULT_SITE_USER_AGENTS
        if site_user_agents is None
        else site_user_agents
    )

    if user_agents:
        interceptor = SiteUserAgentInterceptor(user_agents, profile)
        profile.setUrlRequestInterceptor(interceptor)
        # Keep a Python reference while Qt owns the interceptor.
        profile._site_user_agent_interceptor = interceptor
    if download_path:
        try:
            profile.setDownloadPath(str(download_path))
        except AttributeError:
            pass

    settings = profile.settings()
    defaults = {
        QWebEngineSettings.WebAttribute.JavascriptEnabled: True,
        QWebEngineSettings.WebAttribute.LocalStorageEnabled: True,
        QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows: True,
        QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls: True,
        QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls: True,
        QWebEngineSettings.WebAttribute.PluginsEnabled: True,
        QWebEngineSettings.WebAttribute.PdfViewerEnabled: True,
        QWebEngineSettings.WebAttribute.AutoLoadIconsForPage: True,
        QWebEngineSettings.WebAttribute.ErrorPageEnabled: True,
    }
    if extra_settings:
        defaults.update(extra_settings)
    for attr, enabled in defaults.items():
        settings.setAttribute(attr, enabled)
    return profile
