import sys
import os
import asyncio
from pathlib import Path
sys.path.append(os.getcwd())

from backend.routers.debug import _execution_error_message
from backend.services.precheck import run_micro_execution

def test_cases():
    print("Running _execution_error_message tests...")
    
    # 1. ZeroDivisionError
    err = _execution_error_message(Path("test.py"), "", "ZeroDivisionError: division by zero\n", 1, False)
    assert err is not None, "ZeroDivisionError should not return None!"
    
    # 2. Clean script
    err = _execution_error_message(Path("test.py"), "Hello\n", "", 0, False)
    assert err is None, "Clean script must return None!"
    
    # 3. SyntaxError (usually stderr with exit_code=1)
    err = _execution_error_message(Path("test.py"), "", "SyntaxError: invalid syntax\n", 1, False)
    assert err is not None, "SyntaxError should not return None!"
    
    # 4. Infinite Loop / Timeout
    err = _execution_error_message(Path("test.py"), "Looping...\n", "", -9, True)
    assert err is not None, "Timeout should not return None!"
    
    # 5. Non-zero exit with no string
    err = _execution_error_message(Path("test.py"), "", "", 1, False)
    assert err is not None, "Exit code 1 with empty stderr should not return None!"
    
    print("Testing run_micro_execution...")
    
    # 1. Clean script
    clean_code = "print('Hello')"
    print("Clean script response:", run_micro_execution(clean_code))
    assert run_micro_execution(clean_code) is None
    
    # 2. Zero division
    zero_code = "1 / 0"
    print("Zero division:", run_micro_execution(zero_code))
    assert run_micro_execution(zero_code) is not None
    
    # 3. Timeout
    timeout_code = "while True: pass"
    print("Timeout:", run_micro_execution(timeout_code))
    assert run_micro_execution(timeout_code) is not None

if __name__ == "__main__":
    test_cases()
    print("All tests passed!")
