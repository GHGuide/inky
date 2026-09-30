// InkyBar: Inky in the macOS menu bar. Bot status and Needs-you count, shortcuts that work in any app,
// and a floating command bar (the app's own, in bar mode). Talks to the local engine only.
// Build: native/mac/build.sh    Run: open native/mac/build/InkyBar.app [--args --url http://127.0.0.1:8800]
import AppKit
import Carbon.HIToolbox
import WebKit

let cli = CommandLine.arguments
let BASE: String = {
    if let i = cli.firstIndex(of: "--url"), i + 1 < cli.count { return cli[i + 1] }
    return ProcessInfo.processInfo.environment["INKY_URL"] ?? "http://127.0.0.1:8800"
}()

struct Bot: Decodable { let id: Int; let name: String; let status: String; let mode: String?; let step: String? }
struct EngineState: Decodable { let bots: [Bot]; let needs: Int; let engine: String? }

// ---------------------------------------------------------------- engine API
final class Engine {
    private var token = ""

    // This Mac's own page carries the API token (other devices must pair), so read it from there.
    private func signIn() async throws {
        let (d, _) = try await URLSession.shared.data(from: URL(string: BASE + "/")!)
        let html = String(decoding: d, as: UTF8.self)
        let rx = try NSRegularExpression(pattern: #"name="inky-token" content="([^"]+)""#)
        guard let m = rx.firstMatch(in: html, range: NSRange(html.startIndex..., in: html)),
              let r = Range(m.range(at: 1), in: html) else { throw URLError(.userAuthenticationRequired) }
        token = String(html[r])
    }

    @discardableResult
    func call(_ method: String, _ path: String, _ body: [String: Any]? = nil) async throws -> Data {
        if token.isEmpty { try await signIn() }
        var r = URLRequest(url: URL(string: BASE + path)!, timeoutInterval: 8)
        r.httpMethod = method
        r.setValue(token, forHTTPHeaderField: "X-Inky-Token")
        if let body {
            r.httpBody = try JSONSerialization.data(withJSONObject: body)
            r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let (d, resp) = try await URLSession.shared.data(for: r)
        if (resp as? HTTPURLResponse)?.statusCode == 401 { token = ""; throw URLError(.userAuthenticationRequired) }
        return d
    }
}

// ---------------------------------------------------------------- system-wide shortcuts (Carbon hot keys: no special permission)
var hotkeyActions: [UInt32: () -> Void] = [:]

func installHotkeyHandler() {
    var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
    InstallEventHandler(GetApplicationEventTarget(), { _, event, _ in
        var hk = EventHotKeyID()
        GetEventParameter(event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID), nil,
                          MemoryLayout<EventHotKeyID>.size, nil, &hk)
        DispatchQueue.main.async { hotkeyActions[hk.id]?() }
        return noErr
    }, 1, &spec, nil, nil)
}

/// Returns false when another app already owns the shortcut.
func registerHotkey(_ id: UInt32, key: Int, mods: Int, _ action: @escaping () -> Void) -> Bool {
    var ref: EventHotKeyRef?
    let st = RegisterEventHotKey(UInt32(key), UInt32(mods), EventHotKeyID(signature: OSType(0x494E_4B59), id: id),
                                 GetApplicationEventTarget(), 0, &ref)
    if st == noErr { hotkeyActions[id] = action }
    return st == noErr
}

// ---------------------------------------------------------------- the floating command bar
final class BarPanel: NSPanel {
    override var canBecomeKey: Bool { true }
}

final class App: NSObject, NSApplicationDelegate, NSMenuDelegate, NSWindowDelegate, WKScriptMessageHandler {
    let engine = Engine()
    var item: NSStatusItem!
    var state: EngineState?
    var reachable = false
    var panel: BarPanel!
    var web: WKWebView!
    var barKey = "⌥Space"

    func applicationDidFinishLaunching(_ n: Notification) {
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.image = octopus()
        item.button?.imagePosition = .imageLeft
        item.button?.setAccessibilityLabel("Inky")
        let menu = NSMenu()
        menu.delegate = self
        item.menu = menu
        makePanel()
        installHotkeyHandler()
        if !registerHotkey(1, key: kVK_Space, mods: optionKey, { [weak self] in self?.toggleBar() }) {
            barKey = registerHotkey(1, key: kVK_Space, mods: optionKey | controlKey, { [weak self] in self?.toggleBar() }) ? "⌃⌥Space" : "none"
        }
        keysOK["pause"] = registerHotkey(2, key: kVK_ANSI_P, mods: optionKey | controlKey) { [weak self] in self?.pauseAll() }
        keysOK["stop"] = registerHotkey(3, key: kVK_Escape, mods: optionKey | controlKey) { [weak self] in self?.stopScreens() }
        Timer.scheduledTimer(withTimeInterval: 4, repeats: true) { [weak self] _ in self?.refresh() }
        refresh()
        if cli.contains("--selftest") { DispatchQueue.main.asyncAfter(deadline: .now() + 2) { self.selfTest() } }
    }
    var keysOK: [String: Bool] = [:]

    func refresh() { Task { @MainActor in await refreshNow() } }

    func refreshNow() async {
        do {
            state = try JSONDecoder().decode(EngineState.self, from: try await engine.call("GET", "/api/state"))
            reachable = true
        } catch { reachable = false }
        let n = state?.needs ?? 0
        item.button?.title = !reachable ? " off" : n > 0 ? " \(n)" : ""
        item.button?.setAccessibilityLabel(!reachable ? "Inky is not running" : n > 0 ? "Inky, \(n) need you" : "Inky")
    }

    /// `--selftest [--shot file.png]`: the real code paths, reported as JSON on stdout, then quit.
    func selfTest() {
        Task { @MainActor in
            var r: [String: Any] = ["bar_hotkey": barKey, "other_hotkeys": keysOK]
            await refreshNow()
            r["reachable"] = reachable
            r["needs"] = state?.needs ?? -1
            r["status_title"] = item.button?.title ?? ""
            let m = NSMenu()
            menuNeedsUpdate(m)
            r["menu"] = m.items.map { $0.isSeparatorItem ? "—" : $0.title + ($0.submenu.map { " [" + $0.items.map(\.title).joined(separator: ", ") + "]" } ?? "") }
            hotkeyActions[1]?()  // what pressing the command-bar shortcut runs
            try? await Task.sleep(nanoseconds: 2_500_000_000)
            r["panel_visible"] = panel.isVisible
            r["panel_is_key"] = panel.isKeyWindow
            r["app_active"] = NSApp.isActive
            r["bar"] = (try? await web.evaluateJavaScript("JSON.stringify({open: CMD.open, focused: document.activeElement.id, items: CMD.items.map(i => i.label.replace(/<[^>]+>/g, ''))})")) ?? "no page"
            r["filtered"] = (try? await web.evaluateJavaScript("(() => { const i = document.querySelector('#cmdq'); i.value = '@Flat check the price'; i.dispatchEvent(new Event('input')); return CMD.items.map(i => i.label.replace(/<[^>]+>/g, '')).slice(0, 3).join(' | '); })()")) ?? ""
            if let i = cli.firstIndex(of: "--shot"), i + 1 < cli.count {
                let img: NSImage? = await withCheckedContinuation { c in web.takeSnapshot(with: nil) { im, _ in c.resume(returning: im) } }
                if let tiff = img?.tiffRepresentation, let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) {
                    try? png.write(to: URL(fileURLWithPath: cli[i + 1]))
                    r["shot"] = cli[i + 1]
                }
            }
            _ = try? await web.evaluateJavaScript("closeCmd()")  // Esc in the bar: the page asks the app to hide the panel
            try? await Task.sleep(nanoseconds: 600_000_000)
            r["panel_after_esc"] = panel.isVisible
            hotkeyActions[1]?()
            try? await Task.sleep(nanoseconds: 800_000_000)
            r["reopened"] = panel.isVisible
            hotkeyActions[1]?()
            r["closed_by_shortcut"] = !panel.isVisible
            let d = try! JSONSerialization.data(withJSONObject: r, options: [.prettyPrinted, .sortedKeys])
            FileHandle.standardOutput.write(d)
            exit(0)
        }
    }

    // ------------------------------------------------ menu
    func menuNeedsUpdate(_ menu: NSMenu) {
        menu.removeAllItems()
        guard reachable, let st = state else {
            menu.addItem(disabled("Inky isn’t running at \(BASE)"))
            menu.addItem(disabled("Start it with: python -m inky"))
            menu.addItem(.separator())
            menu.addItem(action("Quit Inky menu bar", #selector(quit), key: "q"))
            return
        }
        menu.addItem(disabled("Inky · \(st.engine ?? "this Mac")"))
        for b in st.bots {
            let it = NSMenuItem(title: "\(b.name) · \(label(b))", action: #selector(openBot(_:)), keyEquivalent: "")
            it.target = self
            it.tag = b.id
            it.image = dot(color(b.status))
            let sub = NSMenu()
            sub.addItem(action("Open", #selector(openBot(_:)), tag: b.id))
            if b.status != "moved" {
                sub.addItem(action("Run now", #selector(runBot(_:)), tag: b.id))
                if ["working", "learning"].contains(b.status) { sub.addItem(action("Pause", #selector(pauseBot(_:)), tag: b.id)) }
                if b.status == "paused" { sub.addItem(action("Resume", #selector(resumeBot(_:)), tag: b.id)) }
                if ["working", "learning", "paused"].contains(b.status) { sub.addItem(action("Stop", #selector(stopBot(_:)), tag: b.id)) }
            }
            it.submenu = sub
            menu.addItem(it)
        }
        if st.bots.isEmpty { menu.addItem(disabled("No bots yet")) }
        menu.addItem(.separator())
        menu.addItem(action(st.needs > 0 ? "Needs you (\(st.needs))" : "Needs you", #selector(openNeeds)))
        menu.addItem(action("Command bar      \(barKey)", #selector(showBar)))
        menu.addItem(action("Pause all bots      ⌃⌥P", #selector(pauseAllItem)))
        menu.addItem(action("Stop everything on my screen      ⌃⌥Esc", #selector(stopScreensItem)))
        menu.addItem(.separator())
        menu.addItem(action("Open Inky", #selector(openHome)))
        menu.addItem(action("Quit Inky menu bar", #selector(quit), key: "q"))
    }

    func label(_ b: Bot) -> String {
        switch b.status {
        case "working", "learning": return (b.step?.isEmpty == false) ? "\(b.status) · \(b.step!)" : b.status
        case "needs_you": return "needs you"
        case "moved": return "on another computer"
        default: return b.status
        }
    }

    func color(_ s: String) -> NSColor {
        switch s {
        case "working": return NSColor(red: 0.18, green: 0.62, blue: 0.36, alpha: 1)
        case "learning", "needs_you": return NSColor(red: 0.91, green: 0.44, blue: 0.32, alpha: 1)
        case "moved": return NSColor(red: 0.23, green: 0.36, blue: 0.86, alpha: 1)
        default: return .tertiaryLabelColor
        }
    }

    func disabled(_ t: String) -> NSMenuItem { let i = NSMenuItem(title: t, action: nil, keyEquivalent: ""); i.isEnabled = false; return i }
    func action(_ t: String, _ sel: Selector, key: String = "", tag: Int = 0) -> NSMenuItem {
        let i = NSMenuItem(title: t, action: sel, keyEquivalent: key); i.target = self; i.tag = tag; return i
    }

    @objc func openBot(_ s: NSMenuItem) { open("#/bot/\(s.tag)/computer") }
    @objc func openNeeds() { open("#/needs") }
    @objc func openHome() { open("#/bots") }
    @objc func showBar() { toggleBar() }
    @objc func pauseAllItem() { pauseAll() }
    @objc func stopScreensItem() { stopScreens() }
    @objc func quit() { NSApp.terminate(nil) }
    @objc func runBot(_ s: NSMenuItem) { send("POST", "/api/bots/\(s.tag)/run", [:]) }
    @objc func pauseBot(_ s: NSMenuItem) { send("POST", "/api/bots/\(s.tag)/control", ["cmd": "pause"]) }
    @objc func resumeBot(_ s: NSMenuItem) { send("POST", "/api/bots/\(s.tag)/control", ["cmd": "resume"]) }
    @objc func stopBot(_ s: NSMenuItem) { send("POST", "/api/bots/\(s.tag)/control", ["cmd": "stop"]) }

    func send(_ m: String, _ p: String, _ body: [String: Any]) {
        Task { @MainActor in _ = try? await engine.call(m, p, body); refresh() }
    }

    func pauseAll() {
        Task { @MainActor in
            for b in state?.bots ?? [] where ["working", "learning"].contains(b.status) {
                _ = try? await engine.call("POST", "/api/bots/\(b.id)/control", ["cmd": "pause"])
            }
            refresh()
        }
    }

    func stopScreens() {  // Esc in the bot's window stops it; this works from any app
        Task { @MainActor in
            for b in state?.bots ?? [] where b.mode == "screen" {
                _ = try? await engine.call("POST", "/api/bots/\(b.id)/control", ["cmd": "stop"])
            }
            refresh()
        }
    }

    func open(_ hash: String) { NSWorkspace.shared.open(URL(string: BASE + "/" + hash)!) }

    // ------------------------------------------------ floating command bar
    func makePanel() {
        panel = BarPanel(contentRect: NSRect(x: 0, y: 0, width: 720, height: 500), styleMask: [.borderless, .nonactivatingPanel],
                         backing: .buffered, defer: false)
        panel.isFloatingPanel = true
        panel.level = .floating
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.hasShadow = false
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.delegate = self
        let cfg = WKWebViewConfiguration()
        cfg.userContentController.add(self, name: "inky")
        web = WKWebView(frame: panel.contentView!.bounds, configuration: cfg)
        web.autoresizingMask = [.width, .height]
        web.setValue(false, forKey: "drawsBackground")
        panel.contentView?.addSubview(web)
        loadBar()
    }

    func loadBar() { web.load(URLRequest(url: URL(string: BASE + "/?bar=1#/bar")!)) }

    func toggleBar() {
        if panel.isVisible { panel.orderOut(nil); return }
        if let f = (NSScreen.main ?? NSScreen.screens.first)?.visibleFrame {
            panel.setFrameOrigin(NSPoint(x: f.midX - 360, y: f.maxY - 500 - f.height * 0.1))
        }
        panel.makeKeyAndOrderFront(nil)  // a non-activating panel takes your typing but leaves your app in front, like Spotlight
        panel.makeFirstResponder(web)
        web.evaluateJavaScript("window.inkyBarOpen ? (inkyBarOpen(), true) : false") { [weak self] r, _ in
            if (r as? Bool) != true { self?.loadBar() }  // the engine wasn't up when we last loaded
        }
    }

    func windowDidResignKey(_ n: Notification) { panel.orderOut(nil) }

    func userContentController(_ c: WKUserContentController, didReceive m: WKScriptMessage) {
        guard let d = m.body as? [String: Any], let t = d["type"] as? String else { return }
        if t == "hide" { panel.orderOut(nil) }
        if t == "open", let h = d["hash"] as? String { panel.orderOut(nil); open(h) }
        refresh()
    }

    // ------------------------------------------------ icons
    func octopus() -> NSImage {
        let img = NSImage(size: NSSize(width: 18, height: 18), flipped: true) { _ in
            NSColor.black.setFill()
            NSBezierPath(ovalIn: NSRect(x: 3.5, y: 1.5, width: 11, height: 9.5)).fill()
            NSColor.black.setStroke()
            for x in [4.5, 7.5, 10.5, 13.5] {
                let p = NSBezierPath()
                p.lineWidth = 1.6
                p.lineCapStyle = .round
                p.move(to: NSPoint(x: x, y: 10))
                p.curve(to: NSPoint(x: x + (x < 9 ? -1.5 : 1.5), y: 16), controlPoint1: NSPoint(x: x, y: 13), controlPoint2: NSPoint(x: x + (x < 9 ? -2 : 2), y: 13.5))
                p.stroke()
            }
            return true
        }
        img.isTemplate = true
        return img
    }

    func dot(_ c: NSColor) -> NSImage {
        NSImage(size: NSSize(width: 10, height: 10), flipped: false) { r in
            c.setFill()
            NSBezierPath(ovalIn: r.insetBy(dx: 1.5, dy: 1.5)).fill()
            return true
        }
    }
}

let app = NSApplication.shared
let delegate = App()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
