import os

def vulnerable_function(user_input):
    # This is a critical security risk (OS Command Injection)
    os.system("ls " + user_input)

if __name__ == "__main__":
    vulnerable_function("; rm -rf /")
