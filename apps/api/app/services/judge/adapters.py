import os
import shutil
import tempfile
from typing import Dict, Any, Optional
from app.core.config import settings
from app.services.judge.sandbox import sandbox, SandboxTimeout, SandboxOutputLimitExceeded, SandboxExecutionError
from app.models.run_submit import RunVerdict

class BaseAdapter:
    def execute(self, source_code: str, input_data: Optional[str]) -> Dict[str, Any]:
        raise NotImplementedError()

class Python3Adapter(BaseAdapter):
    def execute(self, source_code: str, input_data: Optional[str]) -> Dict[str, Any]:
        result_dict = {
            "verdict": RunVerdict.INTERNAL_ERROR,
            "stdout": "",
            "stderr": "",
            "time_ms": 0,
            "memory_kb": 0,
            "compile_error_message": None,
            "runtime_error_message": None
        }

        # Create temporary directory on host
        os.makedirs(settings.JUDGE_TEMP_DIR, exist_ok=True)
        temp_dir = tempfile.mkdtemp(dir=settings.JUDGE_TEMP_DIR)
        
        try:
            # Write source code
            source_path = os.path.join(temp_dir, "main.py")
            with open(source_path, "w", encoding="utf-8") as f:
                f.write(source_code)
                
            # Write input data
            input_path = os.path.join(temp_dir, "input.txt")
            with open(input_path, "w", encoding="utf-8") as f:
                if input_data:
                    f.write(input_data)
                
            # Command to execute
            command = "sh -c 'python3 main.py < input.txt'"
            
            # Execute in sandbox
            try:
                out = sandbox.execute(
                    image="python:3.10-slim",
                    command=command,
                    workdir="/workspace",
                    mounts={temp_dir: "/workspace"}
                )
                
                result_dict["stdout"] = out["stdout"]
                result_dict["stderr"] = out["stderr"]
                result_dict["time_ms"] = out["time_ms"]
                
                if out["exit_code"] == 0:
                    result_dict["verdict"] = RunVerdict.ACCEPTED
                else:
                    result_dict["verdict"] = RunVerdict.RUNTIME_ERROR
                    result_dict["runtime_error_message"] = f"Exited with code {out['exit_code']}"
                    # Simple syntax error normalization for python
                    if "SyntaxError" in out["stderr"]:
                        result_dict["verdict"] = RunVerdict.COMPILE_ERROR
                        result_dict["compile_error_message"] = out["stderr"]
                        result_dict["runtime_error_message"] = None
                        
            except SandboxTimeout:
                result_dict["verdict"] = RunVerdict.TIME_LIMIT_EXCEEDED
            except SandboxOutputLimitExceeded:
                result_dict["verdict"] = RunVerdict.OUTPUT_LIMIT_EXCEEDED
            except SandboxExecutionError as e:
                result_dict["verdict"] = RunVerdict.INTERNAL_ERROR
                result_dict["stderr"] = str(e)
                
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            
        return result_dict

class Cpp17Adapter(BaseAdapter):
    def execute(self, source_code: str, input_data: Optional[str]) -> Dict[str, Any]:
        result_dict = {
            "verdict": RunVerdict.INTERNAL_ERROR,
            "stdout": "",
            "stderr": "",
            "time_ms": 0,
            "memory_kb": 0,
            "compile_error_message": None,
            "runtime_error_message": None
        }

        os.makedirs(settings.JUDGE_TEMP_DIR, exist_ok=True)
        temp_dir = tempfile.mkdtemp(dir=settings.JUDGE_TEMP_DIR)
        
        try:
            source_path = os.path.join(temp_dir, "main.cpp")
            with open(source_path, "w", encoding="utf-8") as f:
                f.write(source_code)
                
            input_path = os.path.join(temp_dir, "input.txt")
            with open(input_path, "w", encoding="utf-8") as f:
                if input_data:
                    f.write(input_data)
                    
            # Compile step
            compile_command = "g++ -std=c++17 -O2 main.cpp -o main"
            try:
                compile_out = sandbox.execute(
                    image="gcc:12",
                    command=compile_command,
                    workdir="/workspace",
                    mounts={temp_dir: "/workspace"}
                )
                if compile_out["exit_code"] != 0:
                    result_dict["verdict"] = RunVerdict.COMPILE_ERROR
                    result_dict["compile_error_message"] = compile_out["stderr"]
                    return result_dict
            except SandboxTimeout:
                result_dict["verdict"] = RunVerdict.COMPILE_ERROR
                result_dict["compile_error_message"] = "Compilation timed out"
                return result_dict
            except Exception as e:
                result_dict["verdict"] = RunVerdict.INTERNAL_ERROR
                result_dict["stderr"] = str(e)
                return result_dict

            # Run step
            run_command = "sh -c './main < input.txt'"
            try:
                run_out = sandbox.execute(
                    image="gcc:12",
                    command=run_command,
                    workdir="/workspace",
                    mounts={temp_dir: "/workspace"}
                )
                
                result_dict["stdout"] = run_out["stdout"]
                result_dict["stderr"] = run_out["stderr"]
                result_dict["time_ms"] = run_out["time_ms"]
                
                if run_out["exit_code"] == 0:
                    result_dict["verdict"] = RunVerdict.ACCEPTED
                else:
                    result_dict["verdict"] = RunVerdict.RUNTIME_ERROR
                    result_dict["runtime_error_message"] = f"Exited with code {run_out['exit_code']}"
                    
            except SandboxTimeout:
                result_dict["verdict"] = RunVerdict.TIME_LIMIT_EXCEEDED
            except SandboxOutputLimitExceeded:
                result_dict["verdict"] = RunVerdict.OUTPUT_LIMIT_EXCEEDED
            except SandboxExecutionError as e:
                result_dict["verdict"] = RunVerdict.INTERNAL_ERROR
                result_dict["stderr"] = str(e)
                
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            
        return result_dict

ADAPTERS = {
    "PYTHON3": Python3Adapter(),
    "CPP17": Cpp17Adapter()
}
