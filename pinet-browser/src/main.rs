use gdk::prelude::*;
use gtk::prelude::*;
use std::cell::Cell;
use std::rc::Rc;
use webkit2gtk::{SettingsExt, WebViewExt};

const EPIPHANY_DARK_CSS: &str = r#"
/* Epiphany Dark UI Recreation */
window {
    background-color: #1e1e1e;
    color: #f0f0f0;
}

headerbar.epiphany-header {
    background: #242424;
    border-bottom: 1px solid #141414;
    min-height: 38px;
    padding: 2px 6px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
}

.nav-btn {
    background: transparent;
    border: none;
    border-radius: 6px;
    min-width: 34px;
    min-height: 34px;
    padding: 4px;
    margin: 1px 2px;
    color: #e0e0e0;
}

.nav-btn:hover {
    background-color: rgba(255, 255, 255, 0.08);
    color: #ffffff;
}

.nav-btn:active {
    background-color: rgba(255, 255, 255, 0.16);
}

.nav-btn:disabled {
    opacity: 0.3;
}

entry.epiphany-url {
    background-color: #303030;
    color: #ffffff;
    border: 1px solid #3c3c3c;
    border-radius: 18px;
    padding: 4px 14px;
    font-size: 13px;
    min-width: 300px;
    transition: all 150ms ease-in-out;
}

entry.epiphany-url:focus {
    background-color: #363636;
    border-color: #3584e4;
    box-shadow: 0 0 0 1px #3584e4;
}

progressbar.epiphany-progress {
    min-height: 2px;
    padding: 0;
    margin: 0;
    background-color: transparent;
    border: none;
}

progressbar.epiphany-progress progress {
    background-color: #3584e4;
    border-radius: 0;
    border: none;
    min-height: 2px;
}
"#;

fn normalize_url(input: &str) -> String {
    let trimmed = input.trim();
    if trimmed.is_empty() {
        return "https://duckduckgo.com".to_string();
    }

    if trimmed.starts_with("http://")
        || trimmed.starts_with("https://")
        || trimmed.starts_with("file://")
        || trimmed.starts_with("about:")
    {
        return trimmed.to_string();
    }

    // Check if it looks like a domain, IP, or localhost
    let is_ip_or_domain = !trimmed.contains(' ')
        && (trimmed.contains('.') || trimmed.starts_with("localhost") || trimmed.contains(':'));

    if is_ip_or_domain {
        if trimmed.starts_with("localhost") || trimmed.starts_with("127.0.0.1") || trimmed.starts_with("192.168.") {
            format!("http://{}", trimmed)
        } else {
            format!("https://{}", trimmed)
        }
    } else {
        // Search DuckDuckGo
        format!(
            "https://duckduckgo.com/?q={}",
            urlencoding::encode(trimmed)
        )
    }
}

const HOME_URL: &str = "https://duckduckgo.com";

fn load_css() {
    let provider = gtk::CssProvider::new();
    if let Err(e) = provider.load_from_data(EPIPHANY_DARK_CSS.as_bytes()) {
        eprintln!("Warning: Failed to load Epiphany CSS: {}", e);
    }
    if let Some(screen) = gdk::Screen::default() {
        gtk::StyleContext::add_provider_for_screen(
            &screen,
            &provider,
            gtk::STYLE_PROVIDER_PRIORITY_APPLICATION,
        );
    }
}

fn build_ui(application: &gtk::Application, initial_url: &str) {
    // Main Window
    let window = gtk::ApplicationWindow::new(application);
    window.set_title("Web");
    window.set_default_size(800, 480);
    window.set_icon_name(Some("org.gnome.Epiphany"));

    // 3. HeaderBar (Epiphany Dark)
    let header = gtk::HeaderBar::new();
    header.set_show_close_button(true);
    header.style_context().add_class("epiphany-header");

    // Left Navigation Box
    let left_box = gtk::Box::new(gtk::Orientation::Horizontal, 2);

    let back_btn = gtk::Button::from_icon_name(Some("go-previous-symbolic"), gtk::IconSize::Button);
    back_btn.style_context().add_class("nav-btn");
    back_btn.set_tooltip_text(Some("Back"));
    back_btn.set_sensitive(false);

    let forward_btn = gtk::Button::from_icon_name(Some("go-next-symbolic"), gtk::IconSize::Button);
    forward_btn.style_context().add_class("nav-btn");
    forward_btn.set_tooltip_text(Some("Forward"));
    forward_btn.set_sensitive(false);

    let reload_btn = gtk::Button::from_icon_name(Some("view-refresh-symbolic"), gtk::IconSize::Button);
    reload_btn.style_context().add_class("nav-btn");
    reload_btn.set_tooltip_text(Some("Reload"));

    let home_btn = gtk::Button::from_icon_name(Some("user-home-symbolic"), gtk::IconSize::Button);
    home_btn.style_context().add_class("nav-btn");
    home_btn.set_tooltip_text(Some("Home"));

    left_box.pack_start(&back_btn, false, false, 0);
    left_box.pack_start(&forward_btn, false, false, 0);
    left_box.pack_start(&reload_btn, false, false, 0);
    left_box.pack_start(&home_btn, false, false, 0);
    header.pack_start(&left_box);

    // Center URL Entry (Capsule shape)
    let url_entry = gtk::Entry::new();
    url_entry.set_placeholder_text(Some("Search or type a URL"));
    url_entry.style_context().add_class("epiphany-url");
    url_entry.set_icon_from_icon_name(
        gtk::EntryIconPosition::Primary,
        Some("channel-secure-symbolic"),
    );
    url_entry.set_hexpand(true);
    header.set_custom_title(Some(&url_entry));

    // Right Controls Box (Zoom & Fullscreen)
    let right_box = gtk::Box::new(gtk::Orientation::Horizontal, 2);

    let zoom_out_btn = gtk::Button::from_icon_name(Some("zoom-out-symbolic"), gtk::IconSize::Button);
    zoom_out_btn.style_context().add_class("nav-btn");
    zoom_out_btn.set_tooltip_text(Some("Zoom Out"));

    let zoom_in_btn = gtk::Button::from_icon_name(Some("zoom-in-symbolic"), gtk::IconSize::Button);
    zoom_in_btn.style_context().add_class("nav-btn");
    zoom_in_btn.set_tooltip_text(Some("Zoom In"));

    let fullscreen_btn = gtk::Button::from_icon_name(Some("view-fullscreen-symbolic"), gtk::IconSize::Button);
    fullscreen_btn.style_context().add_class("nav-btn");
    fullscreen_btn.set_tooltip_text(Some("Toggle Fullscreen"));

    right_box.pack_start(&zoom_out_btn, false, false, 0);
    right_box.pack_start(&zoom_in_btn, false, false, 0);
    right_box.pack_start(&fullscreen_btn, false, false, 0);
    header.pack_end(&right_box);

    window.set_titlebar(Some(&header));

    // 4. WebKit WebView & Settings
    let webview = webkit2gtk::WebView::new();
    if let Some(settings) = WebViewExt::settings(&webview) {
        settings.set_enable_javascript(true);
        settings.set_enable_webgl(true);
        settings.set_enable_smooth_scrolling(true);
        settings.set_hardware_acceleration_policy(webkit2gtk::HardwareAccelerationPolicy::Always);
        settings.set_user_agent(Some(
            "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15 Pinet/1.0",
        ));
    }

    // 5. Progress Bar
    let progress_bar = gtk::ProgressBar::new();
    progress_bar.style_context().add_class("epiphany-progress");
    progress_bar.set_fraction(0.0);
    progress_bar.set_visible(false);

    // 6. Layout Container
    let vbox = gtk::Box::new(gtk::Orientation::Vertical, 0);
    vbox.pack_start(&progress_bar, false, false, 0);
    vbox.pack_start(&webview, true, true, 0);
    window.add(&vbox);

    // 7. Event Handlers
    // Navigation Buttons
    {
        let wv = webview.clone();
        back_btn.connect_clicked(move |_| {
            wv.go_back();
        });
    }
    {
        let wv = webview.clone();
        forward_btn.connect_clicked(move |_| {
            wv.go_forward();
        });
    }
    {
        let wv = webview.clone();
        home_btn.connect_clicked(move |_| {
            wv.load_uri(HOME_URL);
        });
    }

    let is_loading = Rc::new(Cell::new(false));
    {
        let wv = webview.clone();
        let loading_flag = is_loading.clone();
        reload_btn.connect_clicked(move |_| {
            if loading_flag.get() {
                wv.stop_loading();
            } else {
                wv.reload();
            }
        });
    }

    // URL Entry
    {
        let wv = webview.clone();
        url_entry.connect_activate(move |entry| {
            let text = entry.text();
            let target_url = normalize_url(text.as_str());
            wv.load_uri(&target_url);
        });
    }

    // Zoom Controls
    {
        let wv = webview.clone();
        zoom_in_btn.connect_clicked(move |_| {
            let current = wv.zoom_level();
            wv.set_zoom_level(current + 0.15);
        });
    }
    {
        let wv = webview.clone();
        zoom_out_btn.connect_clicked(move |_| {
            let current = wv.zoom_level();
            wv.set_zoom_level((current - 0.15).max(0.4));
        });
    }

    // Fullscreen Toggle
    let is_fullscreen = Rc::new(Cell::new(false));
    {
        let win = window.clone();
        let fs_flag = is_fullscreen.clone();
        fullscreen_btn.connect_clicked(move |_| {
            if fs_flag.get() {
                win.unfullscreen();
                fs_flag.set(false);
            } else {
                win.fullscreen();
                fs_flag.set(true);
            }
        });
    }

    // WebKit Signals
    // Estimated Load Progress
    {
        let pb = progress_bar.clone();
        webview.connect_estimated_load_progress_notify(move |wv| {
            let progress = wv.estimated_load_progress();
            pb.set_fraction(progress);
        });
    }

    // Load State Changed
    {
        let pb = progress_bar.clone();
        let r_btn = reload_btn.clone();
        let b_btn = back_btn.clone();
        let f_btn = forward_btn.clone();
        let loading_flag = is_loading.clone();

        webview.connect_load_changed(move |wv, event| {
            match event {
                webkit2gtk::LoadEvent::Started => {
                    loading_flag.set(true);
                    pb.set_visible(true);
                    pb.set_fraction(0.1);
                    r_btn.set_image(Some(&gtk::Image::from_icon_name(
                        Some("process-stop-symbolic"),
                        gtk::IconSize::Button,
                    )));
                    r_btn.set_tooltip_text(Some("Stop loading"));
                }
                webkit2gtk::LoadEvent::Finished => {
                    loading_flag.set(false);
                    pb.set_visible(false);
                    r_btn.set_image(Some(&gtk::Image::from_icon_name(
                        Some("view-refresh-symbolic"),
                        gtk::IconSize::Button,
                    )));
                    r_btn.set_tooltip_text(Some("Reload"));
                    b_btn.set_sensitive(wv.can_go_back());
                    f_btn.set_sensitive(wv.can_go_forward());
                }
                _ => {}
            }
        });
    }

    // URI notify
    {
        let entry = url_entry.clone();
        webview.connect_uri_notify(move |wv| {
            if let Some(uri) = wv.uri() {
                if !entry.is_focus() {
                    entry.set_text(uri.as_str());
                }
                if uri.starts_with("https://") {
                    entry.set_icon_from_icon_name(
                        gtk::EntryIconPosition::Primary,
                        Some("channel-secure-symbolic"),
                    );
                    entry.set_icon_tooltip_text(
                        gtk::EntryIconPosition::Primary,
                        Some("Connection is secure (HTTPS)"),
                    );
                } else if uri.starts_with("http://") {
                    entry.set_icon_from_icon_name(
                        gtk::EntryIconPosition::Primary,
                        Some("dialog-warning-symbolic"),
                    );
                    entry.set_icon_tooltip_text(
                        gtk::EntryIconPosition::Primary,
                        Some("Connection is not secure (HTTP)"),
                    );
                } else {
                    entry.set_icon_from_icon_name(
                        gtk::EntryIconPosition::Primary,
                        Some("network-workgroup-symbolic"),
                    );
                    entry.set_icon_tooltip_text(gtk::EntryIconPosition::Primary, None);
                }
            }
        });
    }

    // Title notify
    {
        let win = window.clone();
        webview.connect_title_notify(move |wv| {
            if let Some(title) = wv.title() {
                win.set_title(&format!("{} — Web", title));
            } else {
                win.set_title("Web");
            }
        });
    }

    webview.load_uri(&normalize_url(initial_url));

    window.show_all();
}

fn main() {
    // HANDLES_OPEN: links passed on the command line (desktop %u, xdg-open)
    // arrive in `open`; without it GApplication rejects them and exits. A
    // second launch forwards its link to the running instance's `open`.
    let application = gtk::Application::new(
        Some("org.pinet.browser"),
        gio::ApplicationFlags::HANDLES_OPEN,
    );

    application.connect_startup(|_| load_css());
    application.connect_activate(|app| build_ui(app, HOME_URL));
    application.connect_open(|app, files, _hint| {
        for file in files {
            build_ui(app, file.uri().as_str());
        }
    });
    application.run();
}
