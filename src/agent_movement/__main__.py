"""``python -m agent_movement``: the same unified CLI as the ``agent-movement`` console script."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
