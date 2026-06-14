import sys
import os

# Add the project root to Python's module search path so that
# test files inside tests/ can import top-level modules like tools.py.
sys.path.insert(0, os.path.dirname(__file__))
