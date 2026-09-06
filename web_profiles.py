from pathlib import Path

from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings


def build_web_profile(
    name,
    parent,
    storage_path,
    cache_path=None,
    download_path=None,
    extra_settings=None,
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
