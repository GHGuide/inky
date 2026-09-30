fn main() {
    // declare the app's own commands so a capability can allow them for the local engine page
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&["tray", "notify", "bar", "open_needs", "autostart", "app_info", "open_url"]),
    ))
    .expect("failed to run tauri-build");
}
