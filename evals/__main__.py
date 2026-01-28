"""
CLI entry point for evals package.

Usage:
    python -m evals.run [options]

Or simply:
    python -m evals [options]
"""

from evals.run import main

if __name__ == "__main__":
    exit(main())
