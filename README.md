# IQ Pro Layout Tool

> ⚠️ **Temporary, disposable fork.** This is the single-rail variant of the production
> [`cnc-nest-app`](https://github.com/refine-drew/cnc-nest-app), built for the temporary
> single-rail machine. **Bug fixes here are NOT auto-shared with the production tool**, and
> vice versa. Archive/delete this repo when the machine is sold.

Optimize CNC cutting layouts for the single-rail bed.
Load VCarve/`.MMG` G-code files, drag parts onto the rail, detect collisions,
and generate a merged master G-code file.

---

## First Install

### Mac

1. **Install Git** (if not already):
   ```
   xcode-select --install
   ```

2. **Install Python 3** from [python.org](https://python.org)

3. **Clone the repo** in Terminal:
   ```
   git clone https://github.com/refine-drew/iq-pro-layout-tool.git
   ```

4. **Double-click `launch.command`** inside the cloned folder.
   - If macOS blocks it: right-click → Open → Open
   - The launcher checks for Python and installs Flask automatically on first run

5. Your browser opens to [http://localhost:5000](http://localhost:5000) automatically.

### Windows

1. **Install Git** from [git-scm.com](https://git-scm.com)

2. **Install Python 3** from [python.org](https://python.org)
   - Check **"Add Python to PATH"** during installation

3. **Clone the repo** in Command Prompt:
   ```
   git clone https://github.com/refine-drew/iq-pro-layout-tool.git
   ```

4. **Double-click `launch.bat`** inside the cloned folder.
   - The launcher checks for Python and installs Flask automatically on first run

5. Your browser opens to [http://localhost:5000](http://localhost:5000) automatically.

> **Note:** Windows Firewall may ask to allow Python network access — click **Allow**.

---

## Updating

To get the latest version:

- **Mac:** double-click `update.command`
- **Windows:** double-click `update.bat`

The update script pulls the latest code from GitHub and relaunches the app automatically.

---

## Project Structure

```
app.py              Flask application and API routes
config.py           Config loading/saving (cross-platform paths)
config.json         Default application settings
gcode_parser.py     VCarve G-code parser
gcode_generator.py  Master G-code builder (order-of-operations merge)
collision.py        Rectangle overlap collision detection
tool_library.py     Tool registry and diameter resolution
requirements.txt    Python dependencies
templates/          HTML templates
static/             Browser JavaScript and CSS
tests/              Pytest test suite
launch.bat          Windows launcher
launch.command      macOS launcher
update.bat          Windows updater
update.command      macOS updater
```
