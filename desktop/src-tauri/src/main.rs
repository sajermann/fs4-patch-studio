// Desktop shell of FS4 Patch Studio: starts the packaged backend (FastAPI, which also serves the interface) on a
// free local port and shows it in a window. Development stays web-only (start.bat); this is only for packaging.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::os::windows::process::CommandExt;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use tauri::webview::{NewWindowResponse, PageLoadEvent};
use tauri::window::Color;
use tauri::{AppHandle, Manager, RunEvent, Theme, Url, WebviewUrl, WebviewWindow, WebviewWindowBuilder};
use tauri_plugin_opener::OpenerExt;

const CREATE_NO_WINDOW: u32 = 0x0800_0000;
const BACKEND_START_TIMEOUT: Duration = Duration::from_secs(120);

struct Backend(Mutex<Option<Child>>);

/// `data\` next to the executable, installed or portable (the installer puts the app in
/// %LOCALAPPDATA%\FS4 Patch Studio; the uninstaller offers to delete this folder). If the app folder is not
/// writable (e.g. installed under Program Files), %LOCALAPPDATA%\FS4 Patch Studio\data instead.
fn data_dir(app: &AppHandle) -> PathBuf {
    let exe_dir = std::env::current_exe().ok().and_then(|p| p.parent().map(PathBuf::from));
    if let Some(dir) = exe_dir.map(|d| d.join("data")) {
        if writable(&dir) {
            return dir;
        }
    }
    let local = app.path().local_data_dir().expect("no local app data folder");
    local.join("FS4 Patch Studio").join("data")
}

fn writable(dir: &PathBuf) -> bool {
    let probe = dir.join(".write_test");
    let ok = fs::create_dir_all(dir).is_ok() && fs::write(&probe, b"").is_ok();
    let _ = fs::remove_file(probe);
    ok
}

fn backend_exe(app: &AppHandle) -> PathBuf {
    if let Ok(path) = std::env::var("FS4_BACKEND_EXE") {
        return PathBuf::from(path);
    }
    let resources = app.path().resource_dir().expect("no resource folder");
    resources.join("backend").join("fs4-backend.exe")
}

fn free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .and_then(|l| l.local_addr())
        .map(|a| a.port())
        .expect("no free local port")
}

fn start_backend(app: &AppHandle, port: u16) -> std::io::Result<Child> {
    let data = data_dir(app);
    let logs = data.join("logs");
    fs::create_dir_all(&logs)?;
    // the run before stays as backend.prev.log: reopening the app after an error does not erase it
    let current = logs.join("backend.log");
    if current.exists() {
        let _ = fs::rename(&current, logs.join("backend.prev.log"));
    }
    let log = File::create(current)?;
    Command::new(backend_exe(app))
        .args(["--port", &port.to_string(), "--no-browser", "--parent-pid", &std::process::id().to_string()])
        .env("FSMOD_DATA_DIR", &data)
        .env("FSMOD_APP_VERSION", app.package_info().version.to_string())
        .stdin(Stdio::null())
        .stdout(log.try_clone()?)
        .stderr(log)
        .creation_flags(CREATE_NO_WINDOW)
        .spawn()
}

/// Waits for the backend port in the background, then swaps the loading page for the app.
fn open_when_ready(app: AppHandle, window: WebviewWindow, port: u16) {
    thread::spawn(move || {
        let addr = SocketAddr::from(([127, 0, 0, 1], port));
        let started = Instant::now();
        loop {
            if TcpStream::connect_timeout(&addr, Duration::from_millis(500)).is_ok() {
                let url = Url::parse(&format!("http://127.0.0.1:{port}/")).unwrap();
                let _ = window.navigate(url);
                return;
            }
            let exited = app
                .state::<Backend>()
                .0
                .lock()
                .unwrap()
                .as_mut()
                .map_or(true, |child| child.try_wait().map_or(true, |status| status.is_some()));
            if exited || started.elapsed() > BACKEND_START_TIMEOUT {
                let logs = data_dir(&app).join("logs").join("backend.log");
                let path = js_string(&logs.to_string_lossy());
                let _ = window.eval(format!("window.showStartError && window.showStartError({path})"));
                return;
            }
            thread::sleep(Duration::from_millis(250));
        }
    });
}

fn js_string(s: &str) -> String {
    let escaped: String = s
        .chars()
        .map(|c| match c {
            '\\' => "\\\\".to_string(),
            '"' => "\\\"".to_string(),
            c => c.to_string(),
        })
        .collect();
    format!("\"{escaped}\"")
}

/// Opens a link in the default browser, on its own thread (never blocks the WebView2 event that asked for it).
/// Failures go to <data>\logs\desktop.log.
fn open_external(app: &AppHandle, url: &Url) {
    let app = app.clone();
    let url = url.to_string();
    thread::spawn(move || {
        if let Err(e) = app.opener().open_url(url.as_str(), None::<&str>) {
            log(&app, &format!("could not open {url}: {e}"));
        }
    });
}

fn log(app: &AppHandle, message: &str) {
    let path = data_dir(app).join("logs").join("desktop.log");
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(file, "{message}");
    }
}

/// Window and webview background before any page paints (the default is white): the loading page's colours.
fn background(theme: Theme) -> Color {
    match theme {
        Theme::Dark => Color(10, 10, 10, 255),
        _ => Color(255, 255, 255, 255),
    }
}

/// Only the loading page and the local backend open inside the window; any other link opens in the browser.
fn is_internal(url: &Url, port: u16) -> bool {
    match url.host_str() {
        Some("127.0.0.1") => url.port() == Some(port),
        Some("tauri.localhost") => true,
        _ => url.scheme() == "tauri",
    }
}

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        // its click script would call the opener through IPC, which the backend's page (http://127.0.0.1) may not
        // use: target=_blank links then did nothing. Without it they reach on_new_window below.
        .plugin(tauri_plugin_opener::Builder::new().open_js_links_on_click(false).build())
        .manage(Backend(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();
            let port = free_port();
            match start_backend(&handle, port) {
                Ok(child) => *handle.state::<Backend>().0.lock().unwrap() = Some(child),
                Err(e) => eprintln!("backend did not start: {e}"),
            }
            let nav = handle.clone();
            let popup = handle.clone();
            // hidden until the loading page has painted: no white flash while the webview starts
            let window = WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title("FS4 Patch Studio")
                .inner_size(1400.0, 900.0)
                .min_inner_size(1000.0, 650.0)
                .maximized(true)
                .visible(false)
                .on_page_load(|window, payload| {
                    if payload.event() == PageLoadEvent::Finished {
                        let _ = window.show();
                    }
                })
                .on_navigation(move |url| {
                    if is_internal(url, port) {
                        return true;
                    }
                    open_external(&nav, url);
                    false
                })
                .on_new_window(move |url, _features| {
                    open_external(&popup, &url);
                    NewWindowResponse::Deny
                })
                .build()?;
            let _ = window.set_background_color(Some(background(window.theme().unwrap_or(Theme::Light))));
            open_when_ready(handle, window, port);
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building the app");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            if let Some(mut child) = handle.state::<Backend>().0.lock().unwrap().take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    });
}
