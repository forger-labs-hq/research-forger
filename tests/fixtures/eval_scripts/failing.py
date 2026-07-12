"""Fixture evaluator: exits nonzero without writing results."""

import sys

print("something broke", file=sys.stderr)
sys.exit(3)
