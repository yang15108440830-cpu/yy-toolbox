@echo off
cd /d %~dp0
rem 桌面常驻工具：pythonw 无黑窗后台启动（单实例互斥由 app.py 内部保证，重复启动只弹提示）
if not exist .venv\Scripts\pythonw.exe (
    echo [错误] 未找到 .venv，请先执行：D:\dev\env\Python312\python.exe -m venv .venv
    pause
    exit /b 1
)
start "" .venv\Scripts\pythonw.exe app.py
