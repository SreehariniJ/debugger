import sys
import traceback

sys.path.append('./src')
from agents import DebuggingAgents

def run():
    print("Loading models...")
    a = DebuggingAgents()
    print("Models loaded. Generating fix...")
    try:
        fix = a.code_fixer_agent('print(1/0)', 'ZeroDivisionError: division by zero')
        print("FIXED:", fix)
    except Exception as e:
        print("ERROR GENERATING FIX:")
        traceback.print_exc()

if __name__ == '__main__':
    run()
