import traceback
import sys

try:
    import backend.dependencies
    import backend.config
    import src.rag_engine
    import src.agents
    import src.Scanner
    print("Core imports OK")
except Exception:
    traceback.print_exc()
    sys.exit(1)
