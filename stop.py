"""结束监控程序（run.py）和它开的专用 Edge。双击 stop.bat 运行。"""

import subprocess
import time

PS = (
    "Get-CimInstance Win32_Process | Where-Object { "
    "($_.Name -eq 'python.exe' -and $_.CommandLine -match 'run\\.py') -or "
    "($_.Name -eq 'msedge.exe' -and $_.CommandLine -match 'browser-profile') } | "
    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $_.Name }"
)

out = subprocess.run(["powershell", "-NoProfile", "-Command", PS], capture_output=True, text=True).stdout
names = [x for x in out.split() if x]
if any(n.lower() == "python.exe" for n in names):
    print("监控已结束，专用 Edge 也关了。")
elif names:
    print("监控本来就没在跑，顺便关掉了剩下的专用 Edge。")
else:
    print("监控本来就没在跑。")
time.sleep(3)
