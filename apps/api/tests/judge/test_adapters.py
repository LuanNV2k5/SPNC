import pytest
from app.services.judge.adapters import ADAPTERS
from app.models.run_submit import RunVerdict

# ---------------------------------------------------------
# CPP17 tests
# ---------------------------------------------------------

def test_C01_valid_hello_world():
    adapter = ADAPTERS["CPP17"]
    code = '#include <iostream>\nint main() { std::cout << "Hello World"; return 0; }'
    result = adapter.execute(code, None)
    assert result["verdict"] == RunVerdict.ACCEPTED
    assert "Hello World" in result["stdout"]

def test_C02_stdin_consumed_correctly():
    adapter = ADAPTERS["CPP17"]
    code = '#include <iostream>\n#include <string>\nint main() { std::string s; std::cin >> s; std::cout << "Input: " << s; return 0; }'
    result = adapter.execute(code, "test_input")
    assert result["verdict"] == RunVerdict.ACCEPTED
    assert "Input: test_input" in result["stdout"]

def test_C03_stdout_captured():
    adapter = ADAPTERS["CPP17"]
    code = '#include <iostream>\nint main() { std::cout << "out"; std::cerr << "err"; return 0; }'
    result = adapter.execute(code, None)
    assert result["verdict"] == RunVerdict.ACCEPTED
    assert "out" in result["stdout"]
    assert "err" in result["stderr"]

def test_C04_compile_error_normalized():
    adapter = ADAPTERS["CPP17"]
    code = '#include <iostream>\nint main() { std::cout << "missing semicolon" return 0; }'
    result = adapter.execute(code, None)
    assert result["verdict"] == RunVerdict.COMPILE_ERROR
    assert result["compile_error_message"] is not None

def test_C05_runtime_error_normalized():
    adapter = ADAPTERS["CPP17"]
    code = 'int main() { int* p = nullptr; *p = 1; return 0; }'
    result = adapter.execute(code, None)
    assert result["verdict"] == RunVerdict.RUNTIME_ERROR
    assert result["runtime_error_message"] is not None

def test_C06_infinite_loop_timeout():
    adapter = ADAPTERS["CPP17"]
    code = 'int main() { while(true) {} return 0; }'
    result = adapter.execute(code, None)
    assert result["verdict"] == RunVerdict.TIME_LIMIT_EXCEEDED

def test_C07_memory_limit():
    adapter = ADAPTERS["CPP17"]
    # Attempt to allocate huge memory (e.g. 1GB) and touch it
    code = '#include <stdlib.h>\n#include <string.h>\nint main() { while(true) { void* p = malloc(1024*1024); if(p) memset(p, 1, 1024*1024); } return 0; }'
    result = adapter.execute(code, None)
    # The sandbox will kill the container, resulting in a runtime error or exit code.
    assert result["verdict"] in [RunVerdict.RUNTIME_ERROR, RunVerdict.INTERNAL_ERROR, RunVerdict.TIME_LIMIT_EXCEEDED]

def test_C08_output_limit():
    adapter = ADAPTERS["CPP17"]
    code = '#include <iostream>\nint main() { while(true) { std::cout << "A"; } return 0; }'
    result = adapter.execute(code, None)
    assert result["verdict"] in [RunVerdict.OUTPUT_LIMIT_EXCEEDED, RunVerdict.TIME_LIMIT_EXCEEDED]

def test_C09_process_fork_restriction():
    adapter = ADAPTERS["CPP17"]
    code = '#include <unistd.h>\nint main() { while(true) { fork(); } return 0; }'
    result = adapter.execute(code, None)
    assert result["verdict"] in [RunVerdict.RUNTIME_ERROR, RunVerdict.TIME_LIMIT_EXCEEDED]

def test_C10_network_denied():
    adapter = ADAPTERS["CPP17"]
    code = '#include <stdlib.h>\nint main() { int r = system("curl -s http://example.com"); return r == 0 ? 0 : 1; }'
    result = adapter.execute(code, None)
    assert result["verdict"] == RunVerdict.RUNTIME_ERROR

def test_C11_filesystem_restriction():
    adapter = ADAPTERS["CPP17"]
    code = '#include <fstream>\nint main() { std::ofstream f("/root/test.txt"); if(!f.is_open()) return 1; return 0; }'
    result = adapter.execute(code, None)
    assert result["verdict"] == RunVerdict.RUNTIME_ERROR

def test_C12_cpp_standard():
    adapter = ADAPTERS["CPP17"]
    # Check __cplusplus macro
    code = '#include <iostream>\nint main() { if (__cplusplus >= 201703L) return 0; return 1; }'
    result = adapter.execute(code, None)
    assert result["verdict"] == RunVerdict.ACCEPTED

# ---------------------------------------------------------
# PYTHON3 tests
# ---------------------------------------------------------

def test_P01_valid_python_program():
    adapter = ADAPTERS["PYTHON3"]
    code = 'print("Hello World")'
    result = adapter.execute(code, None)
    assert result["verdict"] == RunVerdict.ACCEPTED
    assert "Hello World" in result["stdout"]

def test_P02_stdin_consumed():
    adapter = ADAPTERS["PYTHON3"]
    code = 's = input(); print(f"Input: {s}")'
    result = adapter.execute(code, "test_input")
    assert result["verdict"] == RunVerdict.ACCEPTED
    assert "Input: test_input" in result["stdout"]

def test_P03_stdout_captured():
    adapter = ADAPTERS["PYTHON3"]
    code = 'import sys; print("out"); print("err", file=sys.stderr)'
    result = adapter.execute(code, None)
    assert result["verdict"] == RunVerdict.ACCEPTED
    assert "out" in result["stdout"]
    assert "err" in result["stderr"]

def test_P04_syntax_error_normalized():
    adapter = ADAPTERS["PYTHON3"]
    code = 'print("missing quote)'
    result = adapter.execute(code, None)
    assert result["verdict"] == RunVerdict.COMPILE_ERROR
    assert result["compile_error_message"] is not None

def test_P05_runtime_exception_normalized():
    adapter = ADAPTERS["PYTHON3"]
    code = '1 / 0'
    result = adapter.execute(code, None)
    assert result["verdict"] == RunVerdict.RUNTIME_ERROR

def test_P06_infinite_loop_timeout():
    adapter = ADAPTERS["PYTHON3"]
    code = 'while True: pass'
    result = adapter.execute(code, None)
    assert result["verdict"] == RunVerdict.TIME_LIMIT_EXCEEDED

def test_P07_memory_limit():
    adapter = ADAPTERS["PYTHON3"]
    code = 'a = [];\nwhile True: a.append(" " * 10**6)'
    result = adapter.execute(code, None)
    assert result["verdict"] in [RunVerdict.RUNTIME_ERROR, RunVerdict.INTERNAL_ERROR]

def test_P08_output_limit():
    adapter = ADAPTERS["PYTHON3"]
    code = 'while True: print("A" * 1024)'
    result = adapter.execute(code, None)
    assert result["verdict"] in [RunVerdict.OUTPUT_LIMIT_EXCEEDED, RunVerdict.TIME_LIMIT_EXCEEDED]

def test_P09_process_restriction():
    adapter = ADAPTERS["PYTHON3"]
    code = 'import os\nwhile True: os.fork()'
    result = adapter.execute(code, None)
    assert result["verdict"] == RunVerdict.RUNTIME_ERROR

def test_P10_network_denied():
    adapter = ADAPTERS["PYTHON3"]
    code = 'import urllib.request\nurllib.request.urlopen("http://example.com")'
    result = adapter.execute(code, None)
    assert result["verdict"] == RunVerdict.RUNTIME_ERROR

def test_P11_filesystem_restriction():
    adapter = ADAPTERS["PYTHON3"]
    code = 'open("/root/test.txt", "w").write("test")'
    result = adapter.execute(code, None)
    assert result["verdict"] == RunVerdict.RUNTIME_ERROR

def test_P12_python3_adapter_used():
    adapter = ADAPTERS["PYTHON3"]
    code = 'import sys; sys.exit(0 if sys.version_info.major == 3 else 1)'
    result = adapter.execute(code, None)
    assert result["verdict"] == RunVerdict.ACCEPTED
