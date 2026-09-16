#!/usr/bin/env python3
"""Minimal fullscreen Chromium-engine (QtWebEngine) kiosk window.

Usage: dsi-webkiosk.py <profile-name> <url>

No browser UI, extensions, sync or tabs -- just one page -- which keeps it far
lighter than full Chromium/Firefox on this Pi 3B. Cookies/storage persist per
profile under ~/.local/share/dsi-kiosk/QtWebEngine/<profile-name>.
"""
import sys

from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication


def main():
    if len(sys.argv) != 3:
        print("usage: dsi-webkiosk.py <profile-name> <url>", file=sys.stderr)
        return 1
    name, url = sys.argv[1], sys.argv[2]

    app = QApplication(sys.argv[:1])
    app.setApplicationName("dsi-kiosk")

    profile = QWebEngineProfile(name, app)
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
    )

    view = QWebEngineView()
    view.setPage(QWebEnginePage(profile, view))
    view.setUrl(QUrl(url))
    view.showFullScreen()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
