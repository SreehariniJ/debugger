import traceback
import sys
try:
    import main
    print("MAIN IMPORTED SUCCESSFULLY!")
except BaseException as e:
    with open('error_log2.txt', 'w', encoding='utf-8') as f:
        traceback.print_exc(file=f)
    print("FAILED")
    sys.exit(1)
