"""Domain-specific exceptions mapped to stable CLI exit codes."""


class AgentKitsError(Exception):
    """Base error for expected, actionable failures."""


class ValidationError(AgentKitsError):
    """A manifest, plan, or source failed validation."""


class NotFoundError(AgentKitsError):
    """A requested managed resource does not exist."""


class ConflictError(AgentKitsError):
    """The current target state differs from the approved plan."""


class PolicyError(AgentKitsError):
    """A requested operation violates an explicit safety policy."""
