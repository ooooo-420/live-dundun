"""結束監控程式（run.py）和它開的專用 Edge。雙擊 stop.bat 執行。"""

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
    print("監控已結束，專用 Edge 也關了。")
elif names:
    print("監控本來就沒在跑，順便關掉了剩下的專用 Edge。")
else:
    print("監控本來就沒在跑。")
time.sleep(3)
