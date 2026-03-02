import sys
import os

print("--- DIAGNOSTIC START ---")
try:
    print("Attempting to import app...")
    import app
    print("App imported successfully.")
    print("App attributes:", dir(app.app))
except Exception as e:
    print("FAILED to import app.")
    import traceback
    traceback.print_exc()
print("--- DIAGNOSTIC END ---")
