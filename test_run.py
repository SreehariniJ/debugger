import sys
import os
sys.path.append(os.path.join(r"C:\Users\Sreeharini\offline_debugger", "src"))
print("SYS PATH:", sys.path)
try:
    import Scanner
    print("Scanner success!")
except Exception as e:
    import traceback
    traceback.print_exc()
