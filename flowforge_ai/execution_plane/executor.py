"""
Job Executor — Subprocess Isolation & Timeout Monitoring.

Executes task handlers in isolated subprocesses to bypass GIL limitations
and enable forceful termination on timeout.

Captures stdout/stderr, applies sanitization (secret masking),
and truncates to 100KB.
"""

import io
import json
import logging
import re
import subprocess
import sys
import textwrap
import time
from datetime import datetime
from typing import Optional

from flowforge_ai.execution_plane.task_registry import get_task, is_valid_handler

logger = logging.getLogger("flowforge_ai.executor")

# Sensitive data patterns to mask in log output
SENSITIVE_PATTERNS = [
    (re.compile(r'(?i)(password|secret|token|api_key|apikey|auth)\s*[=:]\s*\S+'), r'\1=***REDACTED***'),
    (re.compile(r'(?i)bearer\s+\S+'), 'Bearer ***REDACTED***'),
    (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), '***EMAIL_REDACTED***'),
]

MAX_LOG_SIZE = 102400  # 100 KB


def sanitize_output(output: str) -> str:
    """Mask sensitive data patterns in log output."""
    for pattern, replacement in SENSITIVE_PATTERNS:
        output = pattern.sub(replacement, output)
    return output


def truncate_output(output: str) -> str:
    """Truncate output to MAX_LOG_SIZE (100 KB)."""
    if len(output) > MAX_LOG_SIZE:
        return output[:MAX_LOG_SIZE] + "\n... [TRUNCATED AT 100KB]"
    return output


def execute_in_subprocess(
    target_handler: str,
    payload: dict,
    timeout_seconds: int = 300
) -> dict:
    """
    Execute a task handler in an isolated subprocess.

    Returns a dict with:
    - success: bool
    - output: str (sanitized, truncated stdout/stderr)
    - result: dict or None (handler return value if successful)
    - error: str or None (error message if failed)
    - timed_out: bool
    """
    # Build a Python script that imports and runs the handler
    script = textwrap.dedent(f"""
import sys
import json

# Add project root to path
sys.path.insert(0, '.')

from flowforge_ai.execution_plane.task_registry import get_task

handler = get_task({target_handler!r})
if handler is None:
    print(json.dumps({{"error": "Handler not found: {target_handler}"}}))
    sys.exit(1)

payload = json.loads({json.dumps(json.dumps(payload))})
try:
    result = handler(payload)
    print(json.dumps({{"success": True, "result": result}}))
except Exception as e:
    print(json.dumps({{"success": False, "error": str(e)}}), file=sys.stderr)
    sys.exit(1)
""").strip()

    timed_out = False
    try:
        process = subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            # Forceful termination on timeout
            process.kill()
            stdout, stderr = process.communicate()
            timed_out = True
            logger.warning(
                f"Handler {target_handler} TIMED OUT after {timeout_seconds}s, "
                f"process killed forcefully."
            )

        # Combine and sanitize output
        combined_output = ""
        if stdout:
            combined_output += stdout
        if stderr:
            combined_output += "\n[STDERR]\n" + stderr

        combined_output = sanitize_output(combined_output)
        combined_output = truncate_output(combined_output)

        if timed_out:
            return {
                "success": False,
                "output": combined_output,
                "result": None,
                "error": f"Execution timed out after {timeout_seconds} seconds.",
                "timed_out": True,
            }

        if process.returncode != 0:
            return {
                "success": False,
                "output": combined_output,
                "result": None,
                "error": stderr.strip() if stderr else f"Process exited with code {process.returncode}",
                "timed_out": False,
            }

        # Parse result from stdout
        try:
            result_data = json.loads(stdout.strip())
            return {
                "success": result_data.get("success", True),
                "output": combined_output,
                "result": result_data.get("result"),
                "error": result_data.get("error"),
                "timed_out": False,
            }
        except json.JSONDecodeError:
            return {
                "success": True,
                "output": combined_output,
                "result": None,
                "error": None,
                "timed_out": False,
            }

    except Exception as e:
        logger.exception(f"Failed to execute handler {target_handler}")
        return {
            "success": False,
            "output": "",
            "result": None,
            "error": str(e),
            "timed_out": False,
        }


def execute_job_inline(
    target_handler: str,
    payload: dict,
) -> dict:
    """
    Execute a task handler inline (same process) for testing/lightweight tasks.
    Falls back to this when subprocess isolation is not needed.
    """
    handler = get_task(target_handler)
    if handler is None:
        return {
            "success": False,
            "output": "",
            "result": None,
            "error": f"Handler not found: {target_handler}",
            "timed_out": False,
        }

    try:
        result = handler(payload)
        return {
            "success": True,
            "output": "",
            "result": result,
            "error": None,
            "timed_out": False,
        }
    except Exception as e:
        return {
            "success": False,
            "output": str(e),
            "result": None,
            "error": str(e),
            "timed_out": False,
        }
