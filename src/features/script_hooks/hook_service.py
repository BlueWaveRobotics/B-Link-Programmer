"""
Pre/Post-Flash Hook Execution Service.
Safely executes external automation scripts or system commands using subprocesses
with strict timeout enforcement and output stream capture.
"""

import os
import subprocess
from typing import Tuple, Optional
from src.common import get_logger

logger = get_logger("HookService")


class HookExecutionResult:
    """
    Data container representing the outcome of a hook script execution.
    """

    def __init__(
        self,
        success: bool,
        exit_code: int,
        stdout_text: str = "",
        stderr_text: str = "",
        execution_time: float = 0.0,
    ):
        self.success = success
        self.exit_code = exit_code
        self.stdout_text = stdout_text.strip()
        self.stderr_text = stderr_text.strip()
        self.execution_time = execution_time


class HookService:
    """
    Service responsible for launching and monitoring external hook scripts.
    """

    @staticmethod
    def execute_hook(
        script_path: str,
        arguments: Optional[list] = None,
        timeout_seconds: int = 15,
    ) -> HookExecutionResult:
        """
        Executes an external script (.py, .bat, .sh) or executable and captures output.
        """
        if not script_path or not os.path.exists(script_path):
            err_msg = f"Hook script file not found: {script_path}"
            logger.error(err_msg)
            return HookExecutionResult(
                success=False,
                exit_code=-1,
                stderr_text=err_msg,
            )

        args_list = [script_path]
        if arguments:
            args_list.extend([str(arg) for arg in arguments])

        # If it is a python script, invoke it using the current python interpreter
        if script_path.endswith(".py"):
            args_list.insert(0, "python")

        logger.info(f"Executing hook script: {' '.join(args_list)}")
        import time

        start_time = time.perf_counter()

        try:
            process = subprocess.run(
                args_list,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            elapsed_time = time.perf_counter() - start_time
            is_success = process.returncode == 0

            if is_success:
                logger.info(
                    f"✔ Hook script completed successfully ({elapsed_time:.2f}s).")
            else:
                logger.warning(
                    f"✖ Hook script failed with return code {process.returncode}."
                )

            return HookExecutionResult(
                success=is_success,
                exit_code=process.returncode,
                stdout_text=process.stdout,
                stderr_text=process.stderr,
                execution_time=elapsed_time,
            )

        except subprocess.TimeoutExpired:
            elapsed_time = time.perf_counter() - start_time
            timeout_msg = (
                f"Hook execution timed out after {timeout_seconds} seconds."
            )
            logger.error(timeout_msg)
            return HookExecutionResult(
                success=False,
                exit_code=-2,
                stderr_text=timeout_msg,
                execution_time=elapsed_time,
            )
        except Exception as exc:
            elapsed_time = time.perf_counter() - start_time
            err_msg = f"Hook execution exception: {str(exc)}"
            logger.error(err_msg)
            return HookExecutionResult(
                success=False,
                exit_code=-3,
                stderr_text=err_msg,
                execution_time=elapsed_time,
            )
