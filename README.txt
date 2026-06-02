IQ Pro Layout Tool
=============
Temporary single-rail fork for the Laguna IQ ATC machine (disposable; not auto-synced
with the production cnc-nest-app).
Optimize CNC cutting layouts on a single-rail 54x24 in bed.
Load VCarve/.MMG G-code files, drag parts onto the rail's 13" slots, detect collisions,
and generate a merged master .mmg file.


WINDOWS SETUP
=============
1. Install Python from python.org
   - Check "Add Python to PATH" during installation

2. Install Git from git-scm.com

3. Open Command Prompt and run:
   git clone https://github.com/refine-drew/iq-pro-layout-tool.git
   cd iq-pro-layout-tool

4. Double-click launch.bat

5. Browser opens automatically at http://localhost:5000

To update: just double-click launch.bat again (pulls latest automatically)

Note: Windows Firewall may ask to allow Python network access — click Allow.


MAC SETUP
=========
1. Python is pre-installed on Mac

2. Install Git (if not already):
   xcode-select --install

3. In Terminal:
   git clone https://github.com/refine-drew/iq-pro-layout-tool.git
   cd iq-pro-layout-tool
   chmod +x launch.command

4. Double-click launch.command
   (If macOS blocks it: right-click → Open → Open)

5. Browser opens automatically at http://localhost:5000

To update: just double-click launch.command again (pulls latest automatically)


PROJECT STRUCTURE
=================
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
