import AppKit
import ApplicationServices
import Foundation

// This helper never posts global synthetic events. It suppresses only mapped
// shortcuts in the selected terminal's focused window when its title contains our unique token,
// then writes action IDs to its parent, which forwards bytes to Jetvim's own PTY.
struct Binding: Decodable {
    let id: String
    let terminal: String
    let aliases: [Alias]?
}
struct Alias: Decodable { let terminal: String }
let codes: [String: Int64] = [
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7,
    "c": 8, "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15,
    "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22,
    "5": 23, "equal": 24, "9": 25, "7": 26, "minus": 27, "8": 28,
    "0": 29, "bracket_right": 30, "o": 31, "u": 32, "bracket_left": 33,
    "i": 34, "p": 35, "enter": 36, "l": 37, "j": 38, "k": 40,
    "comma": 43, "slash": 44, "n": 45, "m": 46, "tab": 48, "space": 49,
    "backspace": 51, "escape": 53, "delete": 117, "left": 123,
    "right": 124, "down": 125, "up": 126, "f1": 122, "f2": 120,
    "f3": 99, "f4": 118, "f5": 96, "f6": 97, "f7": 98, "f8": 100,
    "f9": 101, "f10": 109, "f11": 103, "f12": 111,
]
let modifiers: [String: CGEventFlags] = [
    "super": .maskCommand, "ctrl": .maskControl, "alt": .maskAlternate, "shift": .maskShift,
]
let modifierMask: CGEventFlags = [.maskCommand, .maskControl, .maskAlternate, .maskShift]
var bindings: [String: String] = [:]
var tap: CFMachPort?
var lastShift: Double = 0
var interveningKey = false

// The function modifier also identifies navigation keys, not only a held Fn
// key. Track the actual modifier key separately so plain Shift-arrows retain
// their native line/character selection behavior.
struct FnState {
    var held = false
    mutating func observe(code: Int64, flags: CGEventFlags) {
        if code == 63 { held = flags.contains(.maskSecondaryFn) }
        // Called for modifier changes only. Another modifier change without Fn
        // repairs a missed Fn release; a navigation key's flag cannot set it.
        else if !flags.contains(.maskSecondaryFn) { held = false }
    }
    func pressed(hardware: Bool) -> Bool { held || hardware }
}
var fnState = FnState()
enum NativeNavigation: String, CaseIterable {
    case pageUp = "native:shift-page-up"
    case pageDown = "native:shift-page-down"
    case home = "native:shift-home"
    case end = "native:shift-end"
}
func nativeNavigation(owned: Bool, code: Int64, flags: CGEventFlags, physicalFn: Bool) -> NativeNavigation? {
    guard owned, flags.intersection(modifierMask) == .maskShift else { return nil }
    // Some keyboard layouts/macOS paths translate Fn-arrows before the tap.
    switch code {
    case 116: return .pageUp
    case 121: return .pageDown
    case 115: return .home
    case 119: return .end
    default: break
    }
    guard physicalFn else { return nil }
    switch code {
    case 126: return .pageUp
    case 125: return .pageDown
    case 123: return .home
    case 124: return .end
    default: return nil
    }
}
func checkFnKeys() {
    var checked = 0
    func check(_ condition: Bool) {
        guard condition else { fail("Fn routing self-check failed at case \(checked + 1)") }
        checked += 1
    }
    for (raw, translated, expected) in [(Int64(126), Int64(116), NativeNavigation.pageUp),
                                        (125, 121, .pageDown), (123, 115, .home), (124, 119, .end)] {
        check(nativeNavigation(owned: true, code: raw, flags: .maskShift, physicalFn: true) == expected)
        check(nativeNavigation(owned: true, code: translated, flags: .maskShift, physicalFn: false) == expected)
        check(nativeNavigation(owned: true, code: raw, flags: [.maskShift, .maskSecondaryFn], physicalFn: false) == nil)
        check(nativeNavigation(owned: false, code: raw, flags: .maskShift, physicalFn: true) == nil)
        check(nativeNavigation(owned: false, code: translated, flags: .maskShift, physicalFn: false) == nil)
        for modifiers: CGEventFlags in [[], .maskCommand, .maskAlternate, .maskControl,
                                        [.maskShift, .maskCommand], [.maskShift, .maskAlternate], [.maskShift, .maskControl]] {
            check(nativeNavigation(owned: true, code: raw, flags: modifiers, physicalFn: true) == nil)
        }
    }
    var state = FnState()
    state.observe(code: 126, flags: [.maskShift, .maskSecondaryFn])
    check(!state.pressed(hardware: false))
    state.observe(code: 63, flags: .maskSecondaryFn)
    check(state.pressed(hardware: false))
    state.observe(code: 56, flags: [.maskShift, .maskSecondaryFn])
    check(state.pressed(hardware: false))
    state.observe(code: 63, flags: [])
    check(!state.pressed(hardware: false))
    check(state.pressed(hardware: true))
    state.observe(code: 63, flags: .maskSecondaryFn)
    state.observe(code: 56, flags: [.maskShift, .maskSecondaryFn])
    check(state.pressed(hardware: false))
    // Simulate a dropped Fn release, followed by a Shift modifier change.
    state.observe(code: 56, flags: .maskShift)
    check(!state.pressed(hardware: false))
    state.observe(code: 56, flags: [.maskShift, .maskSecondaryFn])
    check(!state.pressed(hardware: false))
    check(nativeNavigation(owned: true, code: 0, flags: .maskShift, physicalFn: true) == nil)
    print("FN ROUTING OK: \(checked) cases (no event tap)")
    print("NATIVE IDS: " + NativeNavigation.allCases.map({ $0.rawValue }).joined(separator: ","))
}

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}
enum BridgeTarget: String, CaseIterable {
    case warp, terminal
    var name: String { self == .warp ? "Warp" : "Apple Terminal" }
    var launchFlag: String { self == .warp ? "--warp-keys" : "--terminal-keys" }
    func acceptsBundle(_ bundle: String?) -> Bool {
        guard let bundle = bundle else { return false }
        return self == .warp ? bundle.hasPrefix("dev.warp.") : bundle == "com.apple.Terminal"
    }
}
func ownsSession(target: BridgeTarget, bundle: String?, title: String?, token: String) -> Bool {
    guard !token.isEmpty, target.acceptsBundle(bundle), let title = title else { return false }
    return title.contains(token)
}
func checkFocus() {
    var checked = 0
    let token = "Jetvim-focus-check"
    for target in BridgeTarget.allCases {
        let bundle = target == .warp ? "dev.warp.Warp-Stable" : "com.apple.Terminal"
        let other = target == .warp ? "com.apple.Terminal" : "dev.warp.Warp-Stable"
        let lookalike = target == .warp ? "evil.dev.warp.Warp-Stable" : "com.apple.Terminal.fake"
        let cases: [(String?, String?, String, Bool)] = [
            (bundle, token, token, true),
            (bundle, "project — " + token + " — shell", token, true),
            (bundle, "another session", token, false),
            (bundle, nil, token, false),
            (bundle, "", token, false),
            (nil, token, token, false),
            (bundle, token, "", false),
            (other, token, token, false),
            (lookalike, token, token, false),
            ("com.apple.finder", token, token, false),
        ]
        for (candidate, title, session, expected) in cases {
            guard ownsSession(target: target, bundle: candidate, title: title, token: session) == expected
                else { fail("Focus guard self-check failed at case \(checked + 1)") }
            checked += 1
        }
    }
    print("FOCUS GUARD OK: \(checked) cases (no Accessibility or event tap)")
}
guard (3...4).contains(CommandLine.arguments.count) else {
    fail("Usage: keybridge <keymap.json> <session-title> [warp|terminal]")
}
let titleToken = CommandLine.arguments[2]
let targetName = CommandLine.arguments.count == 4 ? CommandLine.arguments[3] : "warp"
let target: BridgeTarget = {
    guard let parsed = BridgeTarget(rawValue: targetName) else { fail("Unknown bridge target: " + targetName) }
    return parsed
}()
guard !titleToken.isEmpty else { fail("Session title must not be empty") }
do {
    let data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
    for binding in try JSONDecoder().decode([Binding].self, from: data) {
      for shortcut in [binding.terminal] + (binding.aliases ?? []).map({ $0.terminal }) {
        let parts = shortcut.split(separator: "+").map(String.init)
        guard let key = parts.last, let code = codes[key] else { fail("Unknown key: " + shortcut) }
        var flags: CGEventFlags = []
        for part in parts.dropLast() {
            guard let modifier = modifiers[part] else { fail("Unknown modifier: " + part) }
            flags.formUnion(modifier)
        }
        let identity = "\(code):\(flags.rawValue)"
        guard bindings[identity] == nil else { fail("Duplicate shortcut: " + shortcut) }
        bindings[identity] = binding.id
      }
    }
} catch { fail("Cannot load keymap: \(error)") }
if titleToken == "--check-keymap" {
    print("KEYMAP OK: \(bindings.count) physical shortcuts")
    exit(0)
}
if titleToken == "--check-fn-keys" { checkFnKeys(); exit(0) }
if titleToken == "--check-focus" { checkFocus(); exit(0) }

func ownsFocus() -> Bool {
    guard let app = NSWorkspace.shared.frontmostApplication,
          target.acceptsBundle(app.bundleIdentifier) else { return false }
    let axApp = AXUIElementCreateApplication(app.processIdentifier)
    var windowValue: CFTypeRef?
    guard AXUIElementCopyAttributeValue(axApp, kAXFocusedWindowAttribute as CFString, &windowValue) == .success,
          let value = windowValue, CFGetTypeID(value) == AXUIElementGetTypeID() else { return false }
    let window = unsafeBitCast(value, to: AXUIElement.self)
    var titleValue: CFTypeRef?
    guard AXUIElementCopyAttributeValue(window, kAXTitleAttribute as CFString, &titleValue) == .success,
          let title = titleValue as? String else { return false }
    return ownsSession(target: target, bundle: app.bundleIdentifier, title: title, token: titleToken)
}
func emit(_ id: String) {
    FileHandle.standardOutput.write(Data((id + "\n").utf8))
}
let callback: CGEventTapCallBack = { _, type, event, _ in
    if type == .tapDisabledByTimeout || type == .tapDisabledByUserInput {
        fnState = FnState()
        if let activeTap = tap { CGEvent.tapEnable(tap: activeTap, enable: true) }
        return Unmanaged.passUnretained(event)
    }
    let code = event.getIntegerValueField(.keyboardEventKeycode)
    if type == .flagsChanged {
        fnState.observe(code: code, flags: event.flags)
        if code == 63 { lastShift = 0; interveningKey = true }
    }
    guard ownsFocus() else { lastShift = 0; return Unmanaged.passUnretained(event) }
    let physicalFn = fnState.pressed(hardware: CGEventSource.keyState(.combinedSessionState, key: 63))
    if type == .flagsChanged {
        let flags = event.flags.intersection(modifierMask)
        if physicalFn { lastShift = 0; return Unmanaged.passUnretained(event) }
        if (code == 56 || code == 60) && flags == .maskShift {
            let now = ProcessInfo.processInfo.systemUptime
            if lastShift > 0 && now - lastShift < 0.35 && !interveningKey {
                emit("everywhere"); lastShift = 0
            } else { lastShift = now; interveningKey = false }
        }
        return Unmanaged.passUnretained(event)
    }
    interveningKey = true
    if let navigation = nativeNavigation(owned: true, code: code, flags: event.flags, physicalFn: physicalFn) {
        emit(navigation.rawValue)
        return nil
    }
    let flags = event.flags.intersection(modifierMask).rawValue
    if let id = bindings["\(code):\(flags)"] {
        emit(id)
        return nil
    }
    return Unmanaged.passUnretained(event)
}

guard AXIsProcessTrusted() else {
    fail("""
    Jetvim's \(target.name) bridge needs permission to intercept its shortcuts.
    Open System Settings > Privacy & Security > Device Control and Data Access (macOS 27+).
    On earlier macOS versions, this permission is named Accessibility.
    Enable \(target.name) or the keybridge helper shown there. If the helper is missing,
    click +, press Command-Shift-G, and enter this full path:
    \(CommandLine.arguments[0])
    Then retry ./jetvim \(target.launchFlag). No settings were changed.
    """)
}
let mask = (CGEventMask(1) << CGEventType.keyDown.rawValue) | (CGEventMask(1) << CGEventType.flagsChanged.rawValue)
tap = CGEvent.tapCreate(tap: .cgSessionEventTap, place: .headInsertEventTap,
    options: .defaultTap, eventsOfInterest: mask, callback: callback, userInfo: nil)
guard let activeTap = tap else { fail("macOS did not allow the keyboard event tap. Check Device Control and Data Access (Accessibility on older macOS) and Input Monitoring permissions.") }
guard let source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, activeTap, 0) else { fail("Cannot create keyboard run loop") }
CFRunLoopAddSource(CFRunLoopGetCurrent(), source, .commonModes)
CGEvent.tapEnable(tap: activeTap, enable: true)
emit("READY")
CFRunLoopRun()
