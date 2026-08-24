"""
Static task handler registry.
Maps target_handler strings to callable Python functions.
Acts as an explicit allow-list preventing arbitrary code execution.
"""

# Registry mapping handler names to callables
_TASK_REGISTRY: dict[str, callable] = {}


def register_task(name: str):
    """Decorator to register a task handler function."""
    def decorator(func):
        _TASK_REGISTRY[name] = func
        return func
    return decorator


def get_task(name: str):
    """Look up a registered task handler by name. Returns None if not found."""
    return _TASK_REGISTRY.get(name)


def list_tasks() -> list[str]:
    """Return all registered task handler names."""
    return list(_TASK_REGISTRY.keys())


def is_valid_handler(name: str) -> bool:
    """Check if a handler name is registered in the allow-list."""
    return name in _TASK_REGISTRY


# --- Built-in demo/test handlers ---

@register_task("tasks.noop")
def noop_handler(payload: dict) -> dict:
    """A no-op handler for testing."""
    return {"status": "ok"}


@register_task("tasks.echo")
def echo_handler(payload: dict) -> dict:
    """Returns the payload as-is for testing."""
    return payload
