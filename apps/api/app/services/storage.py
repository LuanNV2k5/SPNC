import hashlib
from typing import Tuple

class StorageAdapter:
    """Minimal S3/MinIO abstraction for Phase 06."""
    
    def __init__(self, bucket_name: str = "spnc-snapshots"):
        self.bucket_name = bucket_name
        self._memory_store = {}

    def upload_code_snapshot(self, session_id: str, sequence: int, content: str) -> Tuple[str, str]:
        """
        Uploads code content and returns (source_hash, object_key).
        In a real implementation, this streams to S3.
        """
        source_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        object_key = f"snapshots/{session_id}/{sequence}_{source_hash[:8]}.txt"
        
        self._memory_store[object_key] = content
        
        return source_hash, object_key

    def download_code_snapshot(self, object_key: str) -> str:
        """
        Downloads code content by object_key.
        In a real implementation, this streams from S3.
        """
        return self._memory_store.get(object_key, "")

# Singleton instance for injection/usage
storage_adapter = StorageAdapter()
