"""Allow ``python -m agent_kits`` to invoke the CLI."""

from agent_kits.cli.main import main

raise SystemExit(main())
