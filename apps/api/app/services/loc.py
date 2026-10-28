def count_loc(code: str) -> int:
    """System-wide LOC policy: non-blank lines (LF or CRLF). Shared by LOC_ANOMALY and Session.final_loc."""
    return len([line for line in code.splitlines() if line.strip()])
