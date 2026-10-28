import docker
import os
import shutil
import tempfile
import time
from typing import Dict, Any, Optional
from app.core.config import settings

class SandboxTimeout(Exception):
    pass

class SandboxOutputLimitExceeded(Exception):
    pass

class SandboxExecutionError(Exception):
    pass

class Sandbox:
    def __init__(self):
        try:
            self.client = docker.from_env()
        except docker.errors.DockerException:
            self.client = None

    def execute(self, image: str, command: str, workdir: str, mounts: Dict[str, str], input_data: Optional[str] = None, memory_limit_mb: Optional[int] = None) -> Dict[str, Any]:
        """
        Executes a command inside a disposable Docker container with strict limits.
        """
        if not self.client:
            raise SandboxExecutionError("Docker daemon is not available")

        # Map local temp dirs to container mount paths
        volumes = {local_path: {'bind': bind_path, 'mode': 'rw'} for local_path, bind_path in mounts.items()}

        # Per-call memory limit (docs/36 D12), never above the global maximum
        memory_mb = min(memory_limit_mb or settings.JUDGE_MEMORY_LIMIT_MB, settings.JUDGE_MEMORY_LIMIT_MB)
        container = None
        try:
            # Create container explicitly to control limits and networking
            container = self.client.containers.create(
                image=image,
                command=command,
                working_dir=workdir,
                volumes=volumes,
                network_disabled=True,
                mem_limit=f"{memory_mb}m",
                memswap_limit=f"{memory_mb}m",
                cpu_quota=settings.JUDGE_CPU_QUOTA,
                cpu_period=100000,
                pids_limit=settings.JUDGE_PIDS_LIMIT,
                user="1000:1000",
                detach=True,
                stdin_open=True if input_data else False
            )

            container.start()
            
            if input_data:
                # Docker SDK doesn't natively expose a simple way to write to stdin if stdin_open=True. 
                # We can attach to the socket, or just use docker exec / simply write to a file in the volume 
                # and redirect it. To avoid socket complexities, let's assume adapters handle input by writing 
                # an `input.txt` file and passing `< input.txt` to the command, since we control the adapter command.
                pass

            start_time = time.time()
            import requests
            try:
                result = container.wait(timeout=settings.JUDGE_WALL_TIME_LIMIT_SECONDS)
            except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
                raise SandboxTimeout("Execution timed out")
            execution_time = int((time.time() - start_time) * 1000)

            # Extract logs
            logs = container.logs(stdout=True, stderr=True, stream=False)
            if len(logs) > settings.JUDGE_OUTPUT_LIMIT_BYTES:
                raise SandboxOutputLimitExceeded("Output size exceeded configured limits")
            
            # The wait returns {'StatusCode': exit_code}
            exit_code = result.get('StatusCode', -1)
            
            stdout_logs = container.logs(stdout=True, stderr=False, stream=False).decode('utf-8', errors='replace')
            stderr_logs = container.logs(stdout=False, stderr=True, stream=False).decode('utf-8', errors='replace')

            return {
                "exit_code": exit_code,
                "stdout": stdout_logs,
                "stderr": stderr_logs,
                "time_ms": execution_time,
                "memory_kb": 0 # Not easily accessible post-mortem without cadvisor/stats polling
            }

        except docker.errors.ContainerError as e:
            raise SandboxExecutionError(str(e))
        except docker.errors.ImageNotFound as e:
            raise SandboxExecutionError(f"Image not found: {e}")
        except docker.errors.APIError as e:
            raise SandboxExecutionError(f"Docker API error: {e}")
        except docker.errors.NotFound:
             raise SandboxExecutionError(f"Docker container not found during execution")
        # For python-docker wait timeout, it throws requests.exceptions.ReadTimeout or similar.
        # But `wait` timeout raises requests.exceptions.ConnectionError or ReadTimeout.
        except Exception as e:
            # Identify timeout
            if "Timeout" in type(e).__name__ or "timeout" in str(e).lower():
                raise SandboxTimeout("Wall time limit exceeded")
            raise e
        finally:
            if container:
                try:
                    container.kill()
                except Exception:
                    pass
                try:
                    container.remove(force=True)
                except Exception:
                    pass

sandbox = Sandbox()
