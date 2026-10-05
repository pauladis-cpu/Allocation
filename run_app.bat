@echo off
setlocal EnableDelayedExpansion
set "PROJECT_DIR=%~dp0"

REM El entorno de Python se crea en una ruta corta y fija bajo tu carpeta de
REM usuario, NO dentro de la carpeta del proyecto. Motivo: Windows tiene un
REM limite de ~260 caracteres por ruta de archivo, y las carpetas internas de
REM algunos paquetes (streamlit, selenium) son profundas — si el proyecto ya
REM esta en una ruta larga (Desktop\algo\otra_carpeta\...), instalar ahi
REM adentro puede superar ese limite y romper la instalacion.
set "VENV_DIR=%USERPROFILE%\.tp-allocation-venv"

cd /d "%PROJECT_DIR%"

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Preparando la app por primera vez, puede tardar unos minutos...

    REM "py" (el Python Launcher) no siempre esta instalado junto con Python
    REM (por ejemplo, si se instalo desde la Microsoft Store) — probamos varios
    REM comandos antes de asumir que Python no esta instalado.
    set "PYCMD="
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "PYCMD=py -3"

    if not defined PYCMD (
        python --version >nul 2>&1
        if not errorlevel 1 set "PYCMD=python"
    )

    if not defined PYCMD (
        python3 --version >nul 2>&1
        if not errorlevel 1 set "PYCMD=python3"
    )

    if not defined PYCMD (
        echo No se encontro Python instalado en esta PC.
        echo Instalalo desde https://www.python.org/downloads/, tildando "Add python.exe to PATH" durante la instalacion, y volve a ejecutar.
        pause
        exit /b 1
    )

    echo Usando: !PYCMD!
    !PYCMD! -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo No se pudo crear el entorno de Python. Verifica la instalacion de Python y volve a intentar.
        pause
        exit /b 1
    )
)

call "%VENV_DIR%\Scripts\activate.bat"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

REM Precargamos la respuesta al prompt "Email:" que streamlit muestra la
REM primera vez que se usa en una PC — si no, se queda esperando que alguien
REM escriba algo en la consola y el doble clic parece "no hacer nada".
if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
    echo [general] > "%USERPROFILE%\.streamlit\credentials.toml"
    echo email = "" >> "%USERPROFILE%\.streamlit\credentials.toml"
)

REM --server.address=localhost: sin esto, Streamlit escucha en todas las
REM interfaces de red por default (se ve una "Network URL" ademas de la
REM local al arrancar). La app no tiene login propio, asi que cualquiera en
REM la misma red de oficina podria abrirla si no se restringe a esta PC.
streamlit run app.py --server.address=localhost

pause
