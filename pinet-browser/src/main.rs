use gdk::prelude::*;
use gtk::prelude::*;
use std::cell::{Cell, RefCell};
use std::fs;
use std::path::{Path, PathBuf};
use std::rc::Rc;
use webkit2gtk::{
    DownloadExt, FindControllerExt, FindOptions, HardwareAccelerationPolicy, LoadEvent,
    SettingsExt, URIRequestExt, UserContentInjectedFrames, UserContentManagerExt, UserStyleLevel,
    UserStyleSheet, WebContextExt, WebViewExt,
};

// Thin, always-visible page scrollbar at the screen edge. Styled scrollbars are
// classic (not overlay), so they show on a touchscreen without mouse movement.
const SCROLLBAR_CSS: &str = "
::-webkit-scrollbar { width: 12px; height: 12px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
    background-color: rgba(128, 128, 128, 0.6);
    border: 2px solid transparent;
    background-clip: content-box;
    border-radius: 6px;
    min-height: 48px;
}
::-webkit-scrollbar-thumb:active { background-color: rgba(53, 132, 228, 0.9); }
::-webkit-scrollbar-corner { background: transparent; }
";

const APP_NAME: &str = "PINET Browser";
const APP_ICON: &str = "pinet-browser";
const SEARCH_URL: &str = "https://duckduckgo.com/?q=";
const HISTORY_MAX: usize = 50;
const KBD: &str = "/usr/local/bin/pinet-kbd";

const BROWSER_CSS: &str = r#"
window { background-color: #1e1e1e; color: #f0f0f0; }

headerbar.epiphany-header {
    background: #242424;
    border-bottom: 1px solid #141414;
    min-height: 48px;
    padding: 2px 4px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
}

/* Touch targets: 44px minimum on the 800x480 panel. */
.nav-btn {
    background: transparent;
    border: none;
    border-radius: 8px;
    min-width: 44px;
    min-height: 44px;
    padding: 0;
    margin: 0 1px;
    color: #e0e0e0;
}
.nav-btn:hover { background-color: rgba(255, 255, 255, 0.08); color: #ffffff; }
.nav-btn:active { background-color: rgba(255, 255, 255, 0.16); }
.nav-btn:disabled { opacity: 0.3; }
.zoom-label { font-size: 12px; min-width: 52px; }

headerbar button.titlebutton {
    min-width: 44px;
    min-height: 44px;
    padding: 0;
    margin-left: 4px;
}
headerbar button.titlebutton.close {
    background: #c01c28;
    color: #ffffff;
    border-radius: 22px;
}

entry.epiphany-url {
    background-color: #303030;
    color: #ffffff;
    border: 1px solid #3c3c3c;
    border-radius: 20px;
    padding: 6px 12px;
    font-size: 13px;
    min-width: 160px;
    min-height: 32px;
}
entry.epiphany-url:focus {
    background-color: #363636;
    border-color: #3584e4;
    box-shadow: 0 0 0 1px #3584e4;
}

progressbar.epiphany-progress { min-height: 2px; padding: 0; margin: 0; background-color: transparent; border: none; }
progressbar.epiphany-progress progress { background-color: #3584e4; border-radius: 0; border: none; min-height: 2px; }

.findbar { background: #242424; border-bottom: 1px solid #141414; padding: 4px 6px; }
.findbar entry { background-color: #303030; color: #ffffff; border: 1px solid #3c3c3c; border-radius: 18px; padding: 6px 12px; min-height: 32px; }
.find-count { color: #b0b0b0; font-size: 12px; margin: 0 8px; }

/* Floating controls over the page (scroll, exit fullscreen). */
.float-btn {
    background: rgba(20, 20, 20, 0.78);
    color: #f0f0f0;
    border: 1px solid rgba(255, 255, 255, 0.25);
    border-radius: 26px;
    min-width: 52px;
    min-height: 52px;
    padding: 0;
}
.float-btn:active { background: #3584e4; }

.toast {
    background-color: rgba(20, 20, 20, 0.92);
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 18px;
    padding: 10px 18px;
}
"#;

thread_local! {
    // Session history only: nothing about browsing is written to disk.
    static HISTORY: RefCell<Vec<(String, String)>> = RefCell::new(Vec::new());
    // Each window's toast, so a download can report in the window it came from.
    static TOASTS: RefCell<Vec<(glib::WeakRef<webkit2gtk::WebView>, gtk::Label)>> =
        RefCell::new(Vec::new());
}

fn esc(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

fn data_dir() -> PathBuf {
    let d = glib::user_data_dir().join("pinet-browser");
    let _ = fs::create_dir_all(&d);
    d
}

fn bookmarks_file() -> PathBuf {
    data_dir().join("bookmarks.tsv")
}

fn load_bookmarks() -> Vec<(String, String)> {
    fs::read_to_string(bookmarks_file())
        .unwrap_or_default()
        .lines()
        .filter_map(|l| {
            let mut it = l.splitn(2, '\t');
            let url = it.next()?.trim().to_string();
            let title = it.next().unwrap_or("").trim().to_string();
            (!url.is_empty()).then_some((url, title))
        })
        .collect()
}

fn save_bookmarks(list: &[(String, String)]) {
    let body: String = list
        .iter()
        .map(|(u, t)| format!("{}\t{}\n", u, t.replace(['\t', '\n'], " ")))
        .collect();
    let _ = fs::write(bookmarks_file(), body);
}

fn is_bookmarked(uri: &str) -> bool {
    load_bookmarks().iter().any(|(u, _)| u == uri)
}

/// Adds the page, or removes it when it is already bookmarked. Returns the new state.
fn toggle_bookmark(uri: &str, title: &str) -> bool {
    let mut list = load_bookmarks();
    let now = if let Some(i) = list.iter().position(|(u, _)| u == uri) {
        list.remove(i);
        false
    } else {
        list.push((uri.to_string(), title.to_string()));
        true
    };
    save_bookmarks(&list);
    now
}

fn record_history(uri: &str, title: &str) {
    if !(uri.starts_with("http://") || uri.starts_with("https://")) {
        return;
    }
    HISTORY.with(|h| {
        let mut h = h.borrow_mut();
        h.retain(|(u, _)| u != uri);
        h.push((uri.to_string(), title.to_string()));
        let excess = h.len().saturating_sub(HISTORY_MAX);
        h.drain(..excess);
    });
}

fn home_path() -> PathBuf {
    let d = glib::user_cache_dir().join("pinet-browser");
    let _ = fs::create_dir_all(&d);
    d.join("home.html")
}

fn link_list(items: &[(String, String)], empty: &str) -> String {
    if items.is_empty() {
        return format!("<p class=\"empty\">{}</p>", empty);
    }
    let rows: String = items
        .iter()
        .map(|(u, t)| {
            let label = if t.is_empty() { u.as_str() } else { t.as_str() };
            format!(
                "<li><a href=\"{}\"><span>{}</span><small>{}</small></a></li>",
                esc(u),
                esc(label),
                esc(u)
            )
        })
        .collect();
    format!("<ul>{}</ul>", rows)
}

/// Writes the start page (search, bookmarks, this session's history) and returns its URI.
fn home_uri() -> String {
    let bookmarks = load_bookmarks();
    let recent: Vec<(String, String)> =
        HISTORY.with(|h| h.borrow().iter().rev().take(15).cloned().collect());
    let html = format!(
        r#"<!doctype html><html><head><meta charset="utf-8"><title>Home</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body {{ margin: 0; padding: 20px 24px 40px; background: #1e1e1e; color: #f0f0f0;
       font: 16px/1.4 sans-serif; }}
form {{ display: flex; gap: 8px; margin: 4px 0 22px; }}
input {{ flex: 1; font-size: 18px; padding: 12px 18px; border-radius: 24px;
        border: 1px solid #3c3c3c; background: #303030; color: #fff; }}
button {{ font-size: 16px; padding: 0 22px; border-radius: 24px; border: none;
         background: #3584e4; color: #fff; }}
h2 {{ font-size: 13px; letter-spacing: 2px; color: #9a9a9a; margin: 18px 0 8px; }}
ul {{ list-style: none; margin: 0; padding: 0; }}
a {{ display: block; padding: 12px 14px; margin: 6px 0; border-radius: 10px;
    background: #2a2a2a; color: #f0f0f0; text-decoration: none; }}
a:active {{ background: #3584e4; }}
a span {{ display: block; }}
a small {{ display: block; color: #8a8a8a; overflow: hidden; text-overflow: ellipsis;
          white-space: nowrap; }}
.empty {{ color: #8a8a8a; }}
</style></head><body>
<form action="https://duckduckgo.com/" method="get">
<input name="q" placeholder="Search DuckDuckGo" autocomplete="off"><button>Search</button>
</form>
<h2>BOOKMARKS</h2>{}
<h2>RECENT (THIS SESSION)</h2>{}
</body></html>"#,
        link_list(&bookmarks, "Tap the star on any page to bookmark it."),
        link_list(&recent, "Pages you visit appear here until the browser closes.")
    );
    let path = home_path();
    let _ = fs::write(&path, html);
    glib::filename_to_uri(&path, None)
        .map(|u| u.to_string())
        .unwrap_or_else(|_| "https://duckduckgo.com".to_string())
}

fn is_home(uri: &str) -> bool {
    glib::filename_to_uri(home_path(), None)
        .map(|h| h.as_str() == uri)
        .unwrap_or(false)
}

fn normalize_url(input: &str) -> String {
    let trimmed = input.trim();
    if trimmed.is_empty() {
        return home_uri();
    }
    if trimmed.starts_with("http://")
        || trimmed.starts_with("https://")
        || trimmed.starts_with("file://")
        || trimmed.starts_with("about:")
    {
        return trimmed.to_string();
    }
    let is_ip_or_domain = !trimmed.contains(' ')
        && (trimmed.contains('.') || trimmed.starts_with("localhost") || trimmed.contains(':'));
    if is_ip_or_domain {
        if trimmed.starts_with("localhost")
            || trimmed.starts_with("127.0.0.1")
            || trimmed.starts_with("192.168.")
        {
            format!("http://{}", trimmed)
        } else {
            format!("https://{}", trimmed)
        }
    } else {
        format!("{}{}", SEARCH_URL, urlencoding::encode(trimmed))
    }
}

/// Show or hide the PINET on-screen keyboard (wvkbd). `show` is a no-op when it is up.
fn keyboard(action: &str) {
    if let Ok(mut child) = std::process::Command::new(KBD).arg(action).spawn() {
        std::thread::spawn(move || {
            let _ = child.wait();
        });
    }
}

fn show_toast(toast: &gtk::Label, text: &str) {
    toast.set_text(text);
    toast.show();
    let t = toast.clone();
    let shown = text.to_string();
    glib::timeout_add_seconds_local_once(4, move || {
        if t.text().as_str() == shown {
            t.hide();
        }
    });
}

fn toast_for(wv: Option<webkit2gtk::WebView>, text: &str) {
    let Some(wv) = wv else { return };
    TOASTS.with(|list| {
        let mut list = list.borrow_mut();
        list.retain(|(w, _)| w.upgrade().is_some());
        if let Some((_, label)) = list.iter().find(|(w, _)| w.upgrade().as_ref() == Some(&wv)) {
            show_toast(label, text);
        }
    });
}

fn downloads_dir() -> PathBuf {
    let d = glib::user_special_dir(glib::UserDirectory::Downloads)
        .unwrap_or_else(|| glib::home_dir().join("Downloads"));
    let _ = fs::create_dir_all(&d);
    d
}

/// `dir/name`, or `dir/name (2).ext` etc. when that already exists.
fn unique_path(dir: &Path, suggested: &str) -> PathBuf {
    let name = Path::new(suggested)
        .file_name()
        .and_then(|n| n.to_str())
        .filter(|n| !n.is_empty())
        .unwrap_or("download");
    let first = dir.join(name);
    if !first.exists() {
        return first;
    }
    let p = Path::new(name);
    let stem = p.file_stem().and_then(|s| s.to_str()).unwrap_or(name);
    let ext = p.extension().and_then(|e| e.to_str());
    (2..)
        .map(|n| match ext {
            Some(e) => dir.join(format!("{} ({}).{}", stem, n, e)),
            None => dir.join(format!("{} ({})", stem, n)),
        })
        .find(|c| !c.exists())
        .unwrap()
}

fn setup_downloads() {
    let Some(ctx) = webkit2gtk::WebContext::default() else { return };
    ctx.connect_download_started(|_, download| {
        download.connect_decide_destination(|d, suggested| {
            let path = unique_path(&downloads_dir(), suggested);
            if let Ok(uri) = glib::filename_to_uri(&path, None) {
                d.set_destination(&uri);
            }
            true
        });
        // `finished` also fires after a failure; only report success once.
        let failed = Rc::new(Cell::new(false));
        {
            let failed = failed.clone();
            download.connect_failed(move |d, err| {
                failed.set(true);
                toast_for(d.web_view(), &format!("Download failed: {}", err.message()));
            });
        }
        download.connect_finished(move |d| {
            if failed.get() {
                return;
            }
            let name = d
                .destination()
                .and_then(|u| glib::filename_from_uri(&u).ok())
                .and_then(|(p, _)| p.file_name().map(|n| n.to_string_lossy().into_owned()))
                .unwrap_or_else(|| "file".to_string());
            toast_for(d.web_view(), &format!("Saved to Downloads/{}", name));
        });
    });
}

fn load_css() {
    let provider = gtk::CssProvider::new();
    if let Err(e) = provider.load_from_data(BROWSER_CSS.as_bytes()) {
        eprintln!("Warning: failed to load browser CSS: {}", e);
    }
    if let Some(screen) = gdk::Screen::default() {
        gtk::StyleContext::add_provider_for_screen(
            &screen,
            &provider,
            gtk::STYLE_PROVIDER_PRIORITY_APPLICATION,
        );
    }
}

fn icon_button(icon: &str, tooltip: &str, class: &str) -> gtk::Button {
    let b = gtk::Button::from_icon_name(Some(icon), gtk::IconSize::Button);
    b.style_context().add_class(class);
    b.set_tooltip_text(Some(tooltip));
    b
}

/// Handle Enter/Backspace/Ctrl+A by key name. GTK's entry bindings match the
/// hardware keycode through its cached keymap, and virtual keyboards (wvkbd,
/// wtype) swap the keymap at runtime, so those bindings can silently miss while
/// typed letters (which go through the input method) still arrive.
fn robust_entry_keys(entry: &gtk::Entry) {
    entry.connect_key_press_event(|e, ev| {
        use gdk::keys::constants as key;
        let k = ev.keyval();
        let ctrl = ev.state().contains(gdk::ModifierType::CONTROL_MASK);
        if k == key::Return || k == key::KP_Enter || k == key::ISO_Enter {
            e.emit_activate();
        } else if k == key::BackSpace && !ctrl {
            e.emit_backspace();
        } else if ctrl && (k == key::a || k == key::A) {
            e.select_region(0, -1);
        } else {
            return glib::Propagation::Proceed;
        }
        glib::Propagation::Stop
    });
}

fn set_star(btn: &gtk::Button, on: bool) {
    btn.set_image(Some(&gtk::Image::from_icon_name(
        Some(if on { "starred-symbolic" } else { "non-starred-symbolic" }),
        gtk::IconSize::Button,
    )));
    btn.set_tooltip_text(Some(if on { "Remove bookmark" } else { "Bookmark this page" }));
}

fn build_ui(application: &gtk::Application, initial_url: &str) {
    let window = gtk::ApplicationWindow::new(application);
    window.set_title(APP_NAME);
    window.set_default_size(800, 480);
    window.set_icon_name(Some(APP_ICON));

    // Header: navigation | address | page tools | close
    let header = gtk::HeaderBar::new();
    header.set_show_close_button(true);
    header.set_decoration_layout(Some(":close"));
    header.style_context().add_class("epiphany-header");

    let back_btn = icon_button("go-previous-symbolic", "Back", "nav-btn");
    let forward_btn = icon_button("go-next-symbolic", "Forward", "nav-btn");
    let reload_btn = icon_button("view-refresh-symbolic", "Reload", "nav-btn");
    let home_btn = icon_button("user-home-symbolic", "Home", "nav-btn");
    back_btn.set_sensitive(false);
    forward_btn.set_sensitive(false);
    let left_box = gtk::Box::new(gtk::Orientation::Horizontal, 0);
    for b in [&back_btn, &forward_btn, &reload_btn, &home_btn] {
        left_box.pack_start(b, false, false, 0);
    }
    header.pack_start(&left_box);

    let url_entry = gtk::Entry::new();
    url_entry.set_placeholder_text(Some("Search or type a URL"));
    url_entry.style_context().add_class("epiphany-url");
    url_entry.set_hexpand(true);
    robust_entry_keys(&url_entry);
    header.set_custom_title(Some(&url_entry));

    let star_btn = icon_button("non-starred-symbolic", "Bookmark this page", "nav-btn");
    let find_btn = icon_button("edit-find-symbolic", "Find in page", "nav-btn");
    let zoom_out_btn = icon_button("zoom-out-symbolic", "Zoom out", "nav-btn");
    let zoom_btn = gtk::Button::with_label("100%");
    zoom_btn.style_context().add_class("nav-btn");
    zoom_btn.style_context().add_class("zoom-label");
    zoom_btn.set_tooltip_text(Some("Reset zoom"));
    let zoom_in_btn = icon_button("zoom-in-symbolic", "Zoom in", "nav-btn");
    let fullscreen_btn = icon_button("view-fullscreen-symbolic", "Fullscreen", "nav-btn");
    let right_box = gtk::Box::new(gtk::Orientation::Horizontal, 0);
    for b in [&star_btn, &find_btn, &zoom_out_btn, &zoom_btn, &zoom_in_btn, &fullscreen_btn] {
        right_box.pack_start(b, false, false, 0);
    }
    header.pack_end(&right_box);
    window.set_titlebar(Some(&header));

    // Web view
    let webview = webkit2gtk::WebView::new();
    if let Some(settings) = WebViewExt::settings(&webview) {
        settings.set_enable_javascript(true);
        settings.set_enable_webgl(true);
        settings.set_enable_smooth_scrolling(true);
        // The Pi 3's VC4 only does GLES 2; forcing GPU compositing cost memory.
        settings.set_hardware_acceleration_policy(HardwareAccelerationPolicy::OnDemand);
        settings.set_user_agent(Some(
            "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15 Pinet/1.0",
        ));
    }
    if let Some(ucm) = webview.user_content_manager() {
        ucm.add_style_sheet(&UserStyleSheet::new(
            SCROLLBAR_CSS,
            UserContentInjectedFrames::AllFrames,
            UserStyleLevel::User,
            &[],
            &[],
        ));
    }

    // Find bar (hidden until Find / Ctrl+F)
    let find_bar = gtk::Box::new(gtk::Orientation::Horizontal, 4);
    find_bar.style_context().add_class("findbar");
    let find_entry = gtk::Entry::new();
    find_entry.set_placeholder_text(Some("Find in page"));
    find_entry.set_hexpand(true);
    robust_entry_keys(&find_entry);
    let find_count = gtk::Label::new(None);
    find_count.style_context().add_class("find-count");
    let find_prev = icon_button("go-up-symbolic", "Previous match", "nav-btn");
    let find_next = icon_button("go-down-symbolic", "Next match", "nav-btn");
    let find_close = icon_button("window-close-symbolic", "Close find", "nav-btn");
    find_bar.pack_start(&find_entry, true, true, 0);
    find_bar.pack_start(&find_count, false, false, 0);
    for b in [&find_prev, &find_next, &find_close] {
        find_bar.pack_start(b, false, false, 0);
    }

    let progress_bar = gtk::ProgressBar::new();
    progress_bar.style_context().add_class("epiphany-progress");

    // Overlay: page + exit-fullscreen button and toast
    let overlay = gtk::Overlay::new();
    overlay.add(&webview);

    let exit_fs_btn = icon_button("view-restore-symbolic", "Exit fullscreen", "float-btn");
    exit_fs_btn.set_halign(gtk::Align::End);
    exit_fs_btn.set_valign(gtk::Align::Start);
    exit_fs_btn.set_margin_top(10);
    exit_fs_btn.set_margin_end(10);
    overlay.add_overlay(&exit_fs_btn);

    let toast = gtk::Label::new(None);
    toast.style_context().add_class("toast");
    toast.set_halign(gtk::Align::Center);
    toast.set_valign(gtk::Align::End);
    toast.set_margin_bottom(24);
    toast.set_line_wrap(true);
    overlay.add_overlay(&toast);
    TOASTS.with(|t| t.borrow_mut().push((webview.downgrade(), toast.clone())));

    let vbox = gtk::Box::new(gtk::Orientation::Vertical, 0);
    vbox.pack_start(&progress_bar, false, false, 0);
    vbox.pack_start(&find_bar, false, false, 0);
    vbox.pack_start(&overlay, true, true, 0);
    window.add(&vbox);

    // --- Navigation ---
    {
        let wv = webview.clone();
        back_btn.connect_clicked(move |_| wv.go_back());
    }
    {
        let wv = webview.clone();
        forward_btn.connect_clicked(move |_| wv.go_forward());
    }
    {
        let wv = webview.clone();
        home_btn.connect_clicked(move |_| wv.load_uri(&home_uri()));
    }
    let is_loading = Rc::new(Cell::new(false));
    {
        let wv = webview.clone();
        let loading = is_loading.clone();
        reload_btn.connect_clicked(move |_| {
            if loading.get() {
                wv.stop_loading();
            } else {
                wv.reload();
            }
        });
    }

    // --- Address bar: on-screen keyboard while it has focus ---
    {
        let wv = webview.clone();
        url_entry.connect_activate(move |entry| {
            wv.load_uri(&normalize_url(entry.text().as_str()));
            keyboard("hide");
            wv.grab_focus();
        });
    }
    url_entry.connect_focus_in_event(|_, _| {
        keyboard("show");
        glib::Propagation::Proceed
    });

    // --- Zoom: label shows the level, tapping it resets to 100% ---
    {
        let wv = webview.clone();
        zoom_in_btn.connect_clicked(move |_| wv.set_zoom_level((wv.zoom_level() + 0.15).min(3.0)));
    }
    {
        let wv = webview.clone();
        zoom_out_btn.connect_clicked(move |_| wv.set_zoom_level((wv.zoom_level() - 0.15).max(0.4)));
    }
    {
        let wv = webview.clone();
        zoom_btn.connect_clicked(move |_| wv.set_zoom_level(1.0));
    }
    {
        let zb = zoom_btn.clone();
        webview.connect_zoom_level_notify(move |wv| {
            zb.set_label(&format!("{:.0}%", wv.zoom_level() * 100.0));
        });
    }

    // --- Fullscreen: the header hides, so a floating button (and Esc) gets you out ---
    let is_fullscreen = Rc::new(Cell::new(false));
    {
        let win = window.clone();
        let fs = is_fullscreen.clone();
        fullscreen_btn.connect_clicked(move |_| {
            if fs.get() {
                win.unfullscreen();
            } else {
                win.fullscreen();
            }
        });
    }
    {
        let win = window.clone();
        exit_fs_btn.connect_clicked(move |_| win.unfullscreen());
    }
    {
        let fs = is_fullscreen.clone();
        let exit = exit_fs_btn.clone();
        window.connect_window_state_event(move |_, ev| {
            let on = ev.new_window_state().contains(gdk::WindowState::FULLSCREEN);
            fs.set(on);
            exit.set_visible(on);
            glib::Propagation::Proceed
        });
    }

    // --- Bookmarks ---
    {
        let wv = webview.clone();
        star_btn.connect_clicked(move |btn| {
            let Some(uri) = wv.uri() else { return };
            if !(uri.starts_with("http://") || uri.starts_with("https://")) {
                return;
            }
            let title = wv.title().map(|t| t.to_string()).unwrap_or_default();
            set_star(btn, toggle_bookmark(&uri, &title));
        });
    }

    // --- Find in page ---
    let finder = webview.find_controller();
    let find_opts = (FindOptions::CASE_INSENSITIVE | FindOptions::WRAP_AROUND).bits();
    let close_find = {
        let bar = find_bar.clone();
        let count = find_count.clone();
        let fc = finder.clone();
        let wv = webview.clone();
        Rc::new(move || {
            if let Some(fc) = &fc {
                fc.search_finish();
            }
            count.set_text("");
            bar.hide();
            keyboard("hide");
            wv.grab_focus();
        })
    };
    let open_find = {
        let bar = find_bar.clone();
        let entry = find_entry.clone();
        Rc::new(move || {
            bar.show_all();
            entry.grab_focus();
        })
    };
    {
        let bar = find_bar.clone();
        let open = open_find.clone();
        let close = close_find.clone();
        find_btn.connect_clicked(move |_| {
            if bar.is_visible() {
                close();
            } else {
                open();
            }
        });
    }
    {
        let close = close_find.clone();
        find_close.connect_clicked(move |_| close());
    }
    find_entry.connect_focus_in_event(|_, _| {
        keyboard("show");
        glib::Propagation::Proceed
    });
    if let Some(fc) = finder.clone() {
        {
            let fc = fc.clone();
            let count = find_count.clone();
            find_entry.connect_changed(move |e| {
                let text = e.text();
                if text.is_empty() {
                    fc.search_finish();
                    count.set_text("");
                } else {
                    fc.search(text.as_str(), find_opts, 1000);
                }
            });
        }
        {
            let fc = fc.clone();
            find_entry.connect_activate(move |_| fc.search_next());
        }
        {
            let fc = fc.clone();
            find_next.connect_clicked(move |_| fc.search_next());
        }
        {
            let fc = fc.clone();
            find_prev.connect_clicked(move |_| fc.search_previous());
        }
        {
            let count = find_count.clone();
            fc.connect_found_text(move |_, n| {
                count.set_text(&if n == 1 { "1 match".to_string() } else { format!("{} matches", n) });
            });
        }
        {
            let count = find_count.clone();
            fc.connect_failed_to_find_text(move |_| count.set_text("No matches"));
        }
    }

    // --- Keyboard shortcuts (for a USB keyboard; the touch UI does not need them) ---
    {
        let win = window.clone();
        let fs = is_fullscreen.clone();
        let bar = find_bar.clone();
        let open = open_find.clone();
        let close = close_find.clone();
        let entry = url_entry.clone();
        window.connect_key_press_event(move |_, ev| {
            use gdk::keys::constants as key;
            let k = ev.keyval();
            let ctrl = ev.state().contains(gdk::ModifierType::CONTROL_MASK);
            if k == key::Escape && fs.get() {
                win.unfullscreen();
            } else if k == key::Escape && bar.is_visible() {
                close();
            } else if k == key::F11 {
                if fs.get() {
                    win.unfullscreen();
                } else {
                    win.fullscreen();
                }
            } else if ctrl && (k == key::f || k == key::F) {
                open();
            } else if ctrl && (k == key::l || k == key::L) {
                entry.grab_focus();
            } else {
                return glib::Propagation::Proceed;
            }
            glib::Propagation::Stop
        });
    }

    // --- Links that ask for a new tab/window (target=_blank, window.open): open them here ---
    webview.connect_create(|wv, action| {
        if let Some(uri) = action.request().and_then(|r| r.uri()) {
            wv.load_uri(&uri);
        }
        None
    });

    // --- Page state ---
    {
        let wv = webview.clone();
        let pb = progress_bar.clone();
        webview.connect_estimated_load_progress_notify(move |_| {
            pb.set_fraction(wv.estimated_load_progress());
        });
    }
    {
        let pb = progress_bar.clone();
        let r_btn = reload_btn.clone();
        let loading = is_loading.clone();
        webview.connect_load_changed(move |wv, event| match event {
            LoadEvent::Started => {
                loading.set(true);
                pb.set_visible(true);
                pb.set_fraction(0.1);
                r_btn.set_image(Some(&gtk::Image::from_icon_name(
                    Some("process-stop-symbolic"),
                    gtk::IconSize::Button,
                )));
                r_btn.set_tooltip_text(Some("Stop loading"));
            }
            LoadEvent::Finished => {
                loading.set(false);
                pb.set_visible(false);
                r_btn.set_image(Some(&gtk::Image::from_icon_name(
                    Some("view-refresh-symbolic"),
                    gtk::IconSize::Button,
                )));
                r_btn.set_tooltip_text(Some("Reload"));
                if let Some(uri) = wv.uri() {
                    let title = wv.title().map(|t| t.to_string()).unwrap_or_default();
                    record_history(&uri, &title);
                }
            }
            _ => {}
        });
    }
    {
        // Also covers same-page navigations (single-page apps) that never "finish" a load.
        let entry = url_entry.clone();
        let b_btn = back_btn.clone();
        let f_btn = forward_btn.clone();
        let star = star_btn.clone();
        webview.connect_uri_notify(move |wv| {
            b_btn.set_sensitive(wv.can_go_back());
            f_btn.set_sensitive(wv.can_go_forward());
            let Some(uri) = wv.uri() else { return };
            let web = uri.starts_with("http://") || uri.starts_with("https://");
            star.set_sensitive(web);
            set_star(&star, web && is_bookmarked(&uri));
            if !entry.is_focus() {
                entry.set_text(if is_home(&uri) { "" } else { uri.as_str() });
            }
            let (icon, tip) = if uri.starts_with("https://") {
                ("channel-secure-symbolic", Some("Connection is secure (HTTPS)"))
            } else if uri.starts_with("http://") {
                ("dialog-warning-symbolic", Some("Connection is not secure (HTTP)"))
            } else {
                ("user-home-symbolic", None)
            };
            entry.set_icon_from_icon_name(gtk::EntryIconPosition::Primary, Some(icon));
            entry.set_icon_tooltip_text(gtk::EntryIconPosition::Primary, tip);
        });
    }
    {
        let win = window.clone();
        webview.connect_title_notify(move |wv| match wv.title().filter(|t| !t.is_empty()) {
            Some(title) => win.set_title(&format!("{} — {}", title, APP_NAME)),
            None => win.set_title(APP_NAME),
        });
    }

    webview.load_uri(&normalize_url(initial_url));
    window.show_all();
    // Shown on demand only.
    find_bar.hide();
    exit_fs_btn.hide();
    toast.hide();
    progress_bar.hide();
    webview.grab_focus();
}

fn main() {
    // HANDLES_OPEN: links passed on the command line (desktop %u, xdg-open)
    // arrive in `open`; without it GApplication rejects them and exits. A
    // second launch forwards its link to the running instance's `open`.
    let application = gtk::Application::new(
        Some("org.pinet.browser"),
        gio::ApplicationFlags::HANDLES_OPEN,
    );
    application.connect_startup(|_| {
        load_css();
        setup_downloads();
    });
    application.connect_activate(|app| build_ui(app, &home_uri()));
    application.connect_open(|app, files, _hint| {
        for file in files {
            build_ui(app, file.uri().as_str());
        }
    });
    application.run();
}
