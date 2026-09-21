# Judge Architecture

## Overview
Phase 07 introduces the isolated Sandbox Judge system. Untrusted student code is completely fenced and isolated from the primary FastAPI application and any database or message queue credentials.

## Execution Flow
1. **API**: A POST /api/v1/sessions/{session_id}/runs request creates a Run record with status PENDING and enqueues the run ID to Redis.
2. **Queue**: Redis serves as an ephemeral queue. PostgreSQL remains the absolute source of truth.
3. **Worker**: A background Judge process monitors the Redis queue. It claims runs by transitioning them from PENDING to RUNNING via atomic updates.
4. **Sandbox**: The worker executes untrusted code strictly within disposable Docker containers with no network access, memory bounds, PID limits, output bounds, and dropped root capabilities. 
5. **Persistence**: Sandbox execution artifacts (stdout, stderr, compile errors, runtime errors, result codes) are safely collected and stored in the database.

## Architecture

`mermaid
graph TD
    User([Browser / Client]) --> API[FastAPI Web Process]
    API --> DB[(PostgreSQL)]
    API --> Redis[(Redis Queue)]
    
    subgraph Judge System
        Worker[Judge Worker]
        Reconciler[Reconciler Worker]
    end
    
    Redis --> Worker
    Worker --> DB
    Worker --> Docker((Isolated Docker Sandbox))
    Docker --> Worker
    
    Reconciler --> DB
    Reconciler --> Redis
`

## Reconciler & CAS Fencing
Redis delivery is at-least-once, meaning duplicate queue delivery may occur. In failure or crash boundary cases, duplicate physical sandbox execution may occur. However, PostgreSQL remains the durable source of truth. PENDING to RUNNING claims are atomically fenced, and `execution_generation` distinguishes authoritative execution attempts. Stale generations cannot persist results, guaranteeing that only the current authoritative generation and its result is accepted.
- **CAS (Compare-And-Swap)**: Result updates check the execution_generation property to prevent stale writes.
- **Reconciler**: Periodically sweeps the database for runs that have lingered in PENDING or RUNNING beyond a configurable time threshold (e.g. 5 minutes, though this value is purely a configuration parameter, not an immutable business rule). It increments the execution_generation and safely requeues the run.

## Security Controls
The Judge Sandbox implements robust protections against malicious payloads:
- 
etwork disabled
- 
on-root
- limits on cpu, memory, pid, wall_time, and output
- strictly restricted ilesystem (read-only root, tmpfs mounts for /tmp with 
oexec)
- docker socket is completely isolated
- No privileged flags
- No credentials or .env mappings
- Automatic cleanup of containers post-execution.
