// Inky desktop app: starts (or attaches to) the engine, shows the app in its own window, and lives in the
// tray with a Needs-you badge, system-wide shortcuts, a floating command bar, notifications and a desktop buddy.
// The web app tells this side what's going on (invoke "tray"/"notify"); actions go back as small JS calls.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod engine;

use serde::Deserialize;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tauri::image::Image;
use tauri::menu::{IsMenuItem, Menu, MenuItem, PredefinedMenuItem, Submenu};
use tauri::tray::{TrayIcon, TrayIconBuilder};
use tauri::{AppHandle, Manager, RunEvent, WebviewUrl, WebviewWindow, WebviewWindowBuilder, WindowEvent};
use tauri_plugin_autostart::ManagerExt as _;
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};
use tauri_plugin_notification::NotificationExt;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

const TRAY: [&[u8]; 3] = [include_bytes!("../icons/tray-0.png"), include_bytes!("../icons/tray-1.png"), include_bytes!("../icons/tray-2.png")];

#[derive(Deserialize, Clone, Default)]
struct BotLite {
    id: i64,
    name: String,
    status: String,
}

#[derive(Default)]
struct Shared {
    url: Mutex<String>,
    child: Mutex<Option<CommandChild>>,
    bots: Mutex<Vec<BotLite>>,
    needs: Mutex<u32>,
    buddy_on: AtomicBool,
    working: Arc<AtomicBool>,
    open_on_focus: Mutex<Option<String>>,
    pending_files: Mutex<Vec<PathBuf>>,
    bar_key: Mutex<String>,
}

fn home() -> PathBuf {
    std::env::var_os("INKY_HOME").map(PathBuf::from).unwrap_or_else(|| {
        let h = std::env::var_os("HOME").or_else(|| std::env::var_os("USERPROFILE")).unwrap_or_default();
        PathBuf::from(h).join(".inky")
    })
}

fn main_window(app: &AppHandle) -> Option<WebviewWindow> {
    app.get_webview_window("main")
}

/// Run a little JS in the app window (the web app already knows how to pause, run and open things).
fn js(app: &AppHandle, code: &str) {
    if let Some(w) = main_window(app) {
        let _ = w.eval(code);
    }
}

fn show_main(app: &AppHandle, hash: Option<&str>) {
    if let Some(w) = main_window(app) {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
        if let Some(h) = hash {
            let _ = w.eval(&format!("location.hash = {}", serde_json::to_string(h).unwrap()));
        }
    }
}

// ---------------------------------------------------------------- commands the web app calls

#[tauri::command]
fn tray(app: AppHandle, needs: u32, bots: Vec<BotLite>, buddy: bool) {
    let st = app.state::<Shared>();
    st.working.store(bots.iter().any(|b| b.status == "working" || b.status == "learning"), Ordering::Relaxed);
    *st.needs.lock().unwrap() = needs;
    *st.bots.lock().unwrap() = bots;
    st.buddy_on.store(buddy, Ordering::Relaxed);
    refresh_tray(&app);
    set_badge(&app, needs);
    if let Some(b) = app.get_webview_window("buddy") {
        if needs > 0 && buddy {
            place_buddy(&app, &b);
            let _ = b.show();
            let _ = b.eval("window.inkyBuddy && inkyBuddy()");
        } else {
            let _ = b.hide();
        }
    }
}

#[tauri::command]
fn notify(app: AppHandle, title: String, body: String, hash: Option<String>) {
    let _ = app.notification().builder().title(&title).body(&body).show();
    // Desktop notifications can't carry buttons: the next time you come to Inky, it opens the right page.
    *app.state::<Shared>().open_on_focus.lock().unwrap() = hash;
}

#[tauri::command]
fn bar(app: AppHandle, msg: serde_json::Value) {
    let Some(w) = app.get_webview_window("bar") else { return };
    match msg.get("type").and_then(|t| t.as_str()) {
        Some("hide") => {
            let _ = w.hide();
        }
        Some("open") => {
            let _ = w.hide();
            show_main(&app, msg.get("hash").and_then(|h| h.as_str()));
        }
        _ => {}
    }
}

#[tauri::command]
fn open_needs(app: AppHandle) {
    show_main(&app, Some("#/needs"));
}

#[tauri::command]
fn autostart(app: AppHandle, on: Option<bool>) -> bool {
    let a = app.autolaunch();
    match on {
        Some(true) => {
            let _ = a.enable();
        }
        Some(false) => {
            let _ = a.disable();
        }
        None => {}
    }
    a.is_enabled().unwrap_or(false)
}

#[tauri::command]
fn open_url(app: AppHandle, url: String) {
    // links from the engine page open in your own browser, never inside the app window
    if url.starts_with("https://") || url.starts_with("http://") {
        #[allow(deprecated)]
        let _ = app.shell().open(&url, None);
    }
}

#[tauri::command]
fn app_info(app: AppHandle) -> serde_json::Value {
    serde_json::json!({ "bar_key": app.state::<Shared>().bar_key.lock().unwrap().clone(), "version": env!("CARGO_PKG_VERSION") })
}

// ---------------------------------------------------------------- tray, badge, buddy, bar

fn label(status: &str) -> &str {
    match status {
        "needs_you" => "needs you",
        "moved" => "on another computer",
        s => s,
    }
}

fn refresh_tray(app: &AppHandle) {
    let Some(tray) = app.tray_by_id("inky") else { return };
    if let Ok(menu) = build_menu(app) {
        let _ = tray.set_menu(Some(menu));
    }
    let n = *app.state::<Shared>().needs.lock().unwrap();
    let _ = tray.set_title(if n > 0 { Some(format!("{n}")) } else { None::<String> });
    let _ = tray.set_tooltip(Some(if n > 0 { format!("Inky · {n} need you") } else { "Inky".to_string() }));
}

fn build_menu(app: &AppHandle) -> tauri::Result<Menu<tauri::Wry>> {
    let st = app.state::<Shared>();
    let bots = st.bots.lock().unwrap().clone();
    let needs = *st.needs.lock().unwrap();
    let bar_key = st.bar_key.lock().unwrap().clone();
    let menu = Menu::new(app)?;
    menu.append(&MenuItem::with_id(app, "hdr", "Inky", false, None::<&str>)?)?;
    for b in &bots {
        let mut items: Vec<MenuItem<tauri::Wry>> = vec![MenuItem::with_id(app, format!("open:{}", b.id), "Open", true, None::<&str>)?];
        if b.status != "moved" {
            items.push(MenuItem::with_id(app, format!("run:{}", b.id), "Run now", true, None::<&str>)?);
            if b.status == "working" || b.status == "learning" {
                items.push(MenuItem::with_id(app, format!("pause:{}", b.id), "Pause", true, None::<&str>)?);
            }
            if b.status == "paused" {
                items.push(MenuItem::with_id(app, format!("resume:{}", b.id), "Resume", true, None::<&str>)?);
            }
        }
        let refs: Vec<&dyn IsMenuItem<tauri::Wry>> = items.iter().map(|i| i as &dyn IsMenuItem<tauri::Wry>).collect();
        menu.append(&Submenu::with_id_and_items(app, format!("bot:{}", b.id), format!("{} · {}", b.name, label(&b.status)), true, &refs)?)?;
    }
    if bots.is_empty() {
        menu.append(&MenuItem::with_id(app, "none", "No bots yet", false, None::<&str>)?)?;
    }
    menu.append(&PredefinedMenuItem::separator(app)?)?;
    let needs_label = if needs > 0 { format!("Needs you ({needs})") } else { "Needs you".to_string() };
    menu.append(&MenuItem::with_id(app, "needs", needs_label, true, None::<&str>)?)?;
    menu.append(&MenuItem::with_id(app, "bar", format!("Command bar ({bar_key})"), true, None::<&str>)?)?;
    menu.append(&MenuItem::with_id(app, "pauseall", "Pause all bots (⌃⌥P)", true, None::<&str>)?)?;
    menu.append(&MenuItem::with_id(app, "stopscreens", "Stop everything on my screen (⌃⌥Esc)", true, None::<&str>)?)?;
    menu.append(&PredefinedMenuItem::separator(app)?)?;
    menu.append(&MenuItem::with_id(app, "show", "Open Inky", true, None::<&str>)?)?;
    menu.append(&MenuItem::with_id(app, "quit", "Quit Inky", true, Some("CmdOrCtrl+Q"))?)?;
    Ok(menu)
}

fn on_menu(app: &AppHandle, id: &str) {
    let (cmd, arg) = id.split_once(':').unwrap_or((id, ""));
    match cmd {
        "open" => show_main(app, Some(&format!("#/bot/{arg}/computer"))),
        "run" => js(app, &format!("post('/api/bots/{arg}/run', {{}}).then(refreshSoon).catch((e) => toast(e.message))")),
        "pause" | "resume" => js(app, &format!("post('/api/bots/{arg}/control', {{ cmd: '{cmd}' }}).then(refreshSoon)")),
        "needs" => show_main(app, Some("#/needs")),
        "bar" => toggle_bar(app),
        "pauseall" => js(app, "pauseAll()"),
        "stopscreens" => js(app, "stopScreens()"),
        "show" => show_main(app, None),
        "quit" => app.exit(0),
        _ => {}
    }
}

fn set_badge(app: &AppHandle, n: u32) {
    let Some(w) = main_window(app) else { return };
    #[cfg(any(target_os = "macos", target_os = "linux"))]
    let _ = w.set_badge_count(if n > 0 { Some(n as i64) } else { None });
    #[cfg(target_os = "windows")]
    let _ = w.set_overlay_icon(if n > 0 { Image::from_bytes(TRAY[0]).ok() } else { None });
}

fn toggle_bar(app: &AppHandle) {
    let Some(w) = app.get_webview_window("bar") else { return };
    if w.is_visible().unwrap_or(false) {
        let _ = w.hide();
        return;
    }
    if let Ok(Some(m)) = w.current_monitor().or_else(|_| w.primary_monitor()) {
        let (sz, pos, scale) = (m.size(), m.position(), m.scale_factor());
        let x = pos.x as f64 / scale + (sz.width as f64 / scale - 720.0) / 2.0;
        let y = pos.y as f64 / scale + sz.height as f64 / scale * 0.14;
        let _ = w.set_position(tauri::LogicalPosition::new(x, y));
    }
    let _ = w.show();
    let _ = w.set_focus();
    let _ = w.eval("window.inkyBarOpen && inkyBarOpen()");
}

fn place_buddy(_app: &AppHandle, w: &WebviewWindow) {
    if let Ok(Some(m)) = w.primary_monitor() {
        let (sz, pos, scale) = (m.size(), m.position(), m.scale_factor());
        let x = pos.x as f64 / scale + sz.width as f64 / scale - 150.0;
        let y = pos.y as f64 / scale + sz.height as f64 / scale - 190.0;
        let _ = w.set_position(tauri::LogicalPosition::new(x, y));
    }
}

fn animate_tray(app: AppHandle, working: Arc<AtomicBool>) {
    std::thread::spawn(move || {
        let frames: Vec<Image> = TRAY.iter().filter_map(|b| Image::from_bytes(b).ok()).map(|i| i.to_owned()).collect();
        let mut i = 0usize;
        let mut was = false;
        loop {
            std::thread::sleep(Duration::from_millis(380));
            let on = working.load(Ordering::Relaxed);
            if !on && !was {
                continue;
            }
            i = if on { (i + 1) % frames.len() } else { 0 };
            was = on;
            if let Some(t) = app.tray_by_id("inky") {
                let _ = t.set_icon(Some(frames[i].clone()));
                #[cfg(target_os = "macos")]
                let _ = t.set_icon_as_template(true);
            }
        }
    });
}

// ---------------------------------------------------------------- files: double-click an .inky bot file

fn import_files(app: &AppHandle, files: Vec<PathBuf>) {
    for f in files {
        if let Ok(text) = std::fs::read_to_string(&f) {
            js(app, &format!("importFile({})", serde_json::to_string(&text).unwrap()));
        }
    }
    show_main(app, None);
}

// ---------------------------------------------------------------- start

fn start_engine(app: &AppHandle) -> Result<String, String> {
    let home = home();
    if let Some(url) = engine::discover(&home) {
        return Ok(url); // the CLI (or another Inky) already runs on this folder: use it
    }
    let (mut rx, child) = app
        .shell()
        .sidecar("inky-engine")
        .map_err(|e| e.to_string())?
        .args(["--port", "0", "--no-open", "--stop-with-stdin", "--home", &home.to_string_lossy()])
        .spawn()
        .map_err(|e| e.to_string())?;
    *app.state::<Shared>().child.lock().unwrap() = Some(child);
    let (tx, rxu) = std::sync::mpsc::channel::<String>();
    tauri::async_runtime::spawn(async move {
        let mut tx = Some(tx);
        while let Some(ev) = rx.recv().await {
            if let CommandEvent::Stdout(line) = ev {
                if let Some(u) = engine::parse_url(&String::from_utf8_lossy(&line)) {
                    if let Some(t) = tx.take() {
                        let _ = t.send(u);
                    }
                }
            }
        }
    });
    rxu.recv_timeout(Duration::from_secs(45)).map_err(|_| "the engine didn't start in time".to_string())
}

fn build_windows(app: &AppHandle, url: &str) -> tauri::Result<()> {
    let main = main_window(app).expect("main window");
    main.navigate(url.parse().expect("engine url"))?;
    WebviewWindowBuilder::new(app, "bar", WebviewUrl::External(format!("{url}/?bar=1#/bar").parse().unwrap()))
        .title("Inky")
        .inner_size(720.0, 500.0)
        .decorations(false)
        .transparent(true)
        .always_on_top(true)
        .skip_taskbar(true)
        .resizable(false)
        .shadow(false)
        .visible(false)
        .build()?;
    WebviewWindowBuilder::new(app, "buddy", WebviewUrl::External(format!("{url}/?buddy=1#/buddy").parse().unwrap()))
        .title("Inky buddy")
        .inner_size(130.0, 170.0)
        .decorations(false)
        .transparent(true)
        .always_on_top(true)
        .skip_taskbar(true)
        .resizable(false)
        .shadow(false)
        .focused(false)
        .visible(false)
        .build()?;
    Ok(())
}

fn main() {
    let shared = Shared::default();
    let working = shared.working.clone();
    tauri::Builder::default()
        .manage(shared)
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_autostart::init(tauri_plugin_autostart::MacosLauncher::LaunchAgent, None))
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, sc, ev| {
                    if ev.state() != ShortcutState::Pressed {
                        return;
                    }
                    if sc.matches(Modifiers::ALT, Code::Space) || sc.matches(Modifiers::ALT | Modifiers::CONTROL, Code::Space) {
                        toggle_bar(app);
                    } else if sc.matches(Modifiers::ALT | Modifiers::CONTROL, Code::KeyP) {
                        js(app, "pauseAll()");
                    } else if sc.matches(Modifiers::ALT | Modifiers::CONTROL, Code::Escape) {
                        js(app, "stopScreens()");
                    }
                })
                .build(),
        )
        .invoke_handler(tauri::generate_handler![tray, notify, bar, open_needs, autostart, app_info, open_url])
        .setup(move |app| {
            let handle = app.handle().clone();
            // the main window shows a small "waking up" page until the engine answers
            WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title("Inky")
                .inner_size(1280.0, 820.0)
                .min_inner_size(900.0, 600.0)
                .build()?;
            let tray = TrayIconBuilder::with_id("inky")
                .icon(Image::from_bytes(TRAY[0])?)
                .icon_as_template(true)
                .tooltip("Inky")
                .menu(&build_menu(&handle)?)
                .show_menu_on_left_click(true)
                .on_menu_event(|app, e| on_menu(app, e.id.as_ref()))
                .build(app)?;
            let _: &TrayIcon = &tray;
            // system-wide shortcuts. ⌥Space is popular (other apps can grab it even when we register fine),
            // so ⌃⌥Space always opens the bar too.
            let gs = app.global_shortcut();
            let alt = gs.register(Shortcut::new(Some(Modifiers::ALT), Code::Space)).is_ok();
            let ctl = gs.register(Shortcut::new(Some(Modifiers::ALT | Modifiers::CONTROL), Code::Space)).is_ok();
            let bar_key = match (alt, ctl) {
                (true, true) => "⌥Space or ⌃⌥Space",
                (true, false) => "⌥Space",
                (false, true) => "⌃⌥Space",
                _ => "none",
            };
            *app.state::<Shared>().bar_key.lock().unwrap() = bar_key.to_string();
            let _ = gs.register(Shortcut::new(Some(Modifiers::ALT | Modifiers::CONTROL), Code::KeyP));
            let _ = gs.register(Shortcut::new(Some(Modifiers::ALT | Modifiers::CONTROL), Code::Escape));
            animate_tray(handle.clone(), working.clone());
            std::thread::spawn(move || match start_engine(&handle) {
                Ok(url) => {
                    *handle.state::<Shared>().url.lock().unwrap() = url.clone();
                    let h2 = handle.clone();
                    let _ = handle.run_on_main_thread(move || {
                        if let Err(e) = build_windows(&h2, &url) {
                            js(&h2, &format!("window.showError && showError({})", serde_json::to_string(&e.to_string()).unwrap()));
                        }
                        let files: Vec<PathBuf> = std::mem::take(&mut *h2.state::<Shared>().pending_files.lock().unwrap());
                        if !files.is_empty() {
                            let h3 = h2.clone();
                            std::thread::spawn(move || {
                                std::thread::sleep(Duration::from_secs(3));
                                import_files(&h3, files);
                            });
                        }
                    });
                }
                Err(e) => js(&handle, &format!("showError({})", serde_json::to_string(&e).unwrap())),
            });
            Ok(())
        })
        .on_window_event(|w, e| {
            if w.label() == "main" {
                match e {
                    WindowEvent::CloseRequested { api, .. } => {
                        api.prevent_close(); // Inky keeps working in the tray
                        let _ = w.hide();
                    }
                    WindowEvent::Focused(true) => {
                        let app = w.app_handle();
                        if let Some(h) = app.state::<Shared>().open_on_focus.lock().unwrap().take() {
                            js(app, &format!("location.hash = {}", serde_json::to_string(&h).unwrap()));
                        }
                    }
                    _ => {}
                }
            }
            if w.label() == "bar" {
                if let WindowEvent::Focused(false) = e {
                    let _ = w.hide();
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building Inky")
        .run(|app, event| match event {
            #[cfg(target_os = "macos")]
            RunEvent::Reopen { .. } => show_main(app, None),
            #[cfg(any(target_os = "macos", target_os = "ios"))]
            RunEvent::Opened { urls } => {
                let files: Vec<PathBuf> = urls.iter().filter_map(|u| u.to_file_path().ok()).collect();
                if app.state::<Shared>().url.lock().unwrap().is_empty() {
                    app.state::<Shared>().pending_files.lock().unwrap().extend(files);
                } else {
                    import_files(app, files);
                }
            }
            RunEvent::Exit => {
                // only an engine this app started. Ask it to stop politely (a hard kill would orphan the real engine
                // behind PyInstaller's loader); when this process ends its stdin closes and it stops anyway.
                if let Some(c) = app.state::<Shared>().child.lock().unwrap().take() {
                    #[cfg(unix)]
                    let _ = std::process::Command::new("kill").args(["-TERM", &c.pid().to_string()]).status();
                    #[cfg(windows)]
                    drop(c);
                }
            }
            _ => {}
        });
}
