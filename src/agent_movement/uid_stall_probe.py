"""Deliberately uncooperative synthetic worker for timeout/termination test.

The root-owned trusted broker must not invoke a protected effect after this
worker stalls. This script has no network, external tool, or secret access.
"""
while True:
    pass
