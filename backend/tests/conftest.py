import os
import sys

# The app is run as `uvicorn app:app` from backend/, so imports are top-level
# (`from compare...`, `import auth`). Mirror that for tests.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
