@echo off
rem Starts the modding app in development mode (hot reload):
rem   backend: uvicorn with --reload on http://localhost:8765, in its own window (restarts when a .py file changes)
rem   frontend: Vite dev server on http://localhost:5173 (proxies /api to 8765), opened in the browser
rem Close both windows (or Ctrl+C) to stop.
cd /d "%~dp0backend"
python -c "import fastapi, uvicorn, PIL, multipart, numpy" 2>nul || python -m pip install -r requirements.txt
if not exist "%~dp0frontend\node_modules" (
  pushd "%~dp0frontend"
  call npm install
  popd
)
start "FS4 Patch Studio - backend" cmd /k python -m uvicorn fsapi.main:app --host 127.0.0.1 --port 8765 --reload --reload-dir . --reload-dir ..\core\fsmod
cd /d "%~dp0frontend"
call npm run dev -- --open
