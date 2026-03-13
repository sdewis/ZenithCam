# Gemini Workspace Guidelines

## Launching GUI Applications (Qt/Wayland)
When launching GUI applications like `ZenithCam` (PyQt6) or `PlasmaLinux` (Qt6 C++), use the `run_shell_command` tool with `is_background: true` and execute the command directly **without** using `nohup` or `> /tmp/log 2>&1 &` background operators, as those may detach the process from the user's active display session or Wayland socket, causing the app window to be invisible or crash silently.

**Correct Method:**
```bash
# Example for Python/PyQt
cd /home/sean/CodeFolder/ZenithCam_SDK_Integrated/app && source venv/bin/activate && python3 main.py
```
*(With the `is_background: true` flag set on the tool call itself)*

## Known Issues
- When stopping the main thread in PyQt6, ensure `QThread.wait()` is called securely with a timeout and `terminate()` fallback, otherwise the event loop may dump core upon exit.
- When creating PyQt layouts, dynamically shrinking widgets should use a small `minimumSize` to allow the parent layout to scale properly on laptop screens.
