import AppKit
import ApplicationServices
import Foundation

// This helper never posts global synthetic events. It suppresses only mapped
// shortcuts in a Warp window whose accessibility title contains our unique token,
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

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}
guard CommandLine.arguments.count == 3 else { fail("Usage: keybridge <keymap.json> <session-title>") }
let titleToken = CommandLine.arguments[2]
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

func ownsFocus() -> Bool {
    guard let app = NSWorkspace.shared.frontmostApplication,
          app.bundleIdentifier?.hasPrefix("dev.warp.") == true else { return false }
    let axApp = AXUIElementCreateApplication(app.processIdentifier)
    var windowValue: CFTypeRef?
    guard AXUIElementCopyAttributeValue(axApp, kAXFocusedWindowAttribute as CFString, &windowValue) == .success,
          let value = windowValue, CFGetTypeID(value) == AXUIElementGetTypeID() else { return false }
    let window = unsafeBitCast(value, to: AXUIElement.self)
    var titleValue: CFTypeRef?
    guard AXUIElementCopyAttributeValue(window, kAXTitleAttribute as CFString, &titleValue) == .success,
          let title = titleValue as? String else { return false }
    return title.contains(titleToken)
}
func emit(_ id: String) {
    FileHandle.standardOutput.write(Data((id + "\n").utf8))
}
let callback: CGEventTapCallBack = { _, type, event, _ in
    if type == .tapDisabledByTimeout || type == .tapDisabledByUserInput {
        if let activeTap = tap { CGEvent.tapEnable(tap: activeTap, enable: true) }
        return Unmanaged.passUnretained(event)
    }
    guard ownsFocus() else { lastShift = 0; return Unmanaged.passUnretained(event) }
    if type == .flagsChanged {
        let code = event.getIntegerValueField(.keyboardEventKeycode)
        let flags = event.flags.intersection(modifierMask)
        if (code == 56 || code == 60) && flags == .maskShift {
            let now = ProcessInfo.processInfo.systemUptime
            if lastShift > 0 && now - lastShift < 0.35 && !interveningKey {
                emit("everywhere"); lastShift = 0
            } else { lastShift = now; interveningKey = false }
        }
        return Unmanaged.passUnretained(event)
    }
    interveningKey = true
    let code = event.getIntegerValueField(.keyboardEventKeycode)
    let flags = event.flags.intersection(modifierMask).rawValue
    if let id = bindings["\(code):\(flags)"] {
        emit(id)
        return nil
    }
    return Unmanaged.passUnretained(event)
}

guard AXIsProcessTrusted() else {
    fail("""
    Jetvim's Warp bridge needs permission to intercept its shortcuts.
    Open System Settings > Privacy & Security > Device Control and Data Access (macOS 27+).
    On earlier macOS versions, this permission is named Accessibility.
    Enable Warp or the keybridge helper shown there. If the helper is missing,
    click +, press Command-Shift-G, and enter this full path:
    \(CommandLine.arguments[0])
    Then retry ./jetvim --warp-keys. No settings were changed.
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
