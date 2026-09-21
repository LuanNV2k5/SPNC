# 31. Phase 06 — Digital Trace Foundation

## Overview
Phase 06 establishes the core ingestion and replay foundation for the SPNC digital trace mechanism. The system tracks high-resolution, client-side actions within a coding session (practice or exam) to provide teachers with deep observability into student problem-solving processes.

## Capabilities

### Trace Ingestion
- **Event Types**: Captures `EDITOR_CHANGED`, `CURSOR_MOVED`, `SELECTION_CHANGED`, `EXECUTION_STARTED`, etc.
- **Batching**: Client buffers events and sends them periodically to reduce network overhead.
- **Idempotency**: The system enforces `(session_id, sequence_number)` uniqueness to handle network retries safely without causing duplicate trace entries.
- **Idempotency Strategy**: 
    - The repository layer detects duplicates by querying the sequence numbers before insertion. 
    - If the same sequence number with the exact same fingerprint is received, it is treated as a safe duplicate and silently ignored.
    - If a duplicate sequence number with a conflicting fingerprint is received, a `TraceConflictError` (409) is returned, and the batch is aborted.
- **Data Deduplication**: A 32-bit `xxhash` canonical fingerprint is calculated to detect content divergence and resolve conflicts safely.

### Session Snapshots
- Captures explicit checkpoints for `RUN`, `SUBMIT`, `TEST`, and `MANUAL_SAVE` reasons.
- Snapshots record the entire state of the editor (language, source_code, line_count).
- Snapshots are stored transparently in blob storage (mocked locally, abstract interface ready for S3).
- Ensures durability for execution verification.

### Trace Replay (Teacher Observability)
- **Teacher Access**: Teachers can replay the trace history of any session that belongs to a class they own.
- **State Resolution**: Gap detection ensures the replay does not proceed beyond the highest contiguous sequence, preventing state corruption during replay if an event was dropped in transit.
- Retrieves paginated event history sorted monotonically by `sequence_number ASC`.
- Supports resuming replay through cursor parameters.

## Storage
- **Relational DB**: Trace metadata, sequence ordering, and indexing.
- **Blob Storage (Abstracted)**: Large artifacts (snapshots) use content-addressable storage paths to optimize cost and performance.

## Architecture
- `app/schemas/trace.py`: Pydantic definitions for Trace and Snapshot APIs.
- `app/models/trace.py`: SQLAlchemy schema mappings.
- `app/repositories/trace.py`: High-throughput DB insertion and sequence integrity checks.
- `app/services/trace.py`: Gap detection, fingerprinting, and session context validation.
- `app/services/storage.py`: Abstract `StorageAdapter` interface for blob interactions.
- `app/api/endpoints/trace.py`: Authorized REST routes for ingestion and observability.
