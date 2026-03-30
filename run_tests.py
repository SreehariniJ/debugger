import pytest
import sys

if __name__ == "__main__":
    retcode = pytest.main(["tests/test_api_endpoints.py"])
    sys.exit(retcode)
