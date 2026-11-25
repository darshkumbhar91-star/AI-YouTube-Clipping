"""
Skill Context - Shared context management for skills.
Provides resource management, caching, and cross-skill communication.
"""

import asyncio
import logging
import hashlib
import json
import pickle
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Callable, TypeVar, Generic
from contextlib import asynccontextmanager
import weakref


logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class SkillContext:
    """Context for a single skill execution."""
    skill_name: str
    execution_id: str
    config: Dict[str, Any]
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None
    status: str = "running"
    error: Optional[str] = None
    
    def complete(self, outputs: Dict[str, Any], error: Optional[str] = None):
        self.outputs = outputs
        self.completed_at = datetime.now().isoformat()
        self.duration_ms = int((
            datetime.fromisoformat(self.completed_at) - 
            datetime.fromisoformat(self.started_at)
        ).total_seconds() * 1000)
        self.status = "failed" if error else "completed"
        self.error = error
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "execution_id": self.execution_id,
            "config": self.config,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "metadata": self.metadata,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "error": self.error,
        }


class ResourceManager:
    """Manages shared resources across skills (GPU, API quotas, file handles, etc.)."""
    
    def __init__(self):
        self._resources: Dict[str, Any] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._quotas: Dict[str, Dict[str, Any]] = {}
        self._usage: Dict[str, Dict[str, int]] = {}
        self._cleanup_callbacks: List[Callable] = []
    
    def register_resource(self, name: str, resource: Any, cleanup: Optional[Callable] = None):
        """Register a shared resource."""
        self._resources[name] = resource
        self._locks[name] = asyncio.Lock()
        if cleanup:
            self._cleanup_callbacks.append(cleanup)
        logger.debug(f"Registered resource: {name}")
    
    def get_resource(self, name: str) -> Any:
        """Get a shared resource."""
        return self._resources.get(name)
    
    @asynccontextmanager
    async def acquire(self, name: str, timeout: float = 30.0):
        """Acquire exclusive access to a resource."""
        if name not in self._locks:
            self._locks[name] = asyncio.Lock()
        
        lock = self._locks[name]
        try:
            await asyncio.wait_for(lock.acquire(), timeout=timeout)
            yield self._resources.get(name)
        finally:
            lock.release()
    
    def set_quota(self, name: str, limit: int, period_seconds: int = 3600):
        """Set rate limit quota for a resource."""
        self._quotas[name] = {
            "limit": limit,
            "period": period_seconds,
            "window_start": datetime.now(),
        }
        self._usage[name] = {"count": 0}
    
    async def check_quota(self, name: str, cost: int = 1) -> bool:
        """Check and consume quota."""
        if name not in self._quotas:
            return True
        
        quota = self._quotas[name]
        usage = self._usage[name]
        
        # Reset window if expired
        if datetime.now() - quota["window_start"] > timedelta(seconds=quota["period"]):
            quota["window_start"] = datetime.now()
            usage["count"] = 0
        
        if usage["count"] + cost > quota["limit"]:
            return False
        
        usage["count"] += cost
        return True
    
    def get_quota_remaining(self, name: str) -> int:
        """Get remaining quota."""
        if name not in self._quotas:
            return -1  # Unlimited
        quota = self._quotas[name]
        usage = self._usage[name]
        return max(0, quota["limit"] - usage["count"])
    
    async def cleanup(self):
        """Cleanup all resources."""
        for callback in self._cleanup_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error(f"Resource cleanup failed: {e}")
        self._resources.clear()
        self._locks.clear()
        self._quotas.clear()
        self._usage.clear()


class CacheBackend(ABC):
    """Abstract cache backend."""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        pass
    
    @abstractmethod
    async def delete(self, key: str):
        pass
    
    @abstractmethod
    async def clear(self):
        pass


class MemoryCache(CacheBackend):
    """In-memory cache with TTL support."""
    
    def __init__(self, max_size: int = 1000):
        self._cache: Dict[str, tuple[Any, Optional[datetime]]] = {}
        self._max_size = max_size
        self._access_times: Dict[str, datetime] = {}
    
    async def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        
        value, expiry = self._cache[key]
        if expiry and datetime.now() > expiry:
            await self.delete(key)
            return None
        
        self._access_times[key] = datetime.now()
        return value
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        if len(self._cache) >= self._max_size and key not in self._cache:
            # Evict LRU
            lru_key = min(self._access_times, key=self._access_times.get)
            await self.delete(lru_key)
        
        expiry = datetime.now() + timedelta(seconds=ttl) if ttl else None
        self._cache[key] = (value, expiry)
        self._access_times[key] = datetime.now()
    
    async def delete(self, key: str):
        self._cache.pop(key, None)
        self._access_times.pop(key, None)
    
    async def clear(self):
        self._cache.clear()
        self._access_times.clear()


class DiskCache(CacheBackend):
    """Disk-based cache with persistence."""
    
    def __init__(self, cache_dir: Path, max_size_mb: int = 500):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self._index: Dict[str, Dict] = {}
        self._load_index()
    
    def _load_index(self):
        index_file = self.cache_dir / "index.json"
        if index_file.exists():
            with open(index_file) as f:
                self._index = json.load(f)
    
    def _save_index(self):
        index_file = self.cache_dir / "index.json"
        with open(index_file, 'w') as f:
            json.dump(self._index, f)
    
    def _get_path(self, key: str) -> Path:
        hashed = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self.cache_dir / f"{hashed}.cache"
    
    async def get(self, key: str) -> Optional[Any]:
        if key not in self._index:
            return None
        
        entry = self._index[key]
        if entry.get("expiry") and datetime.now() > datetime.fromisoformat(entry["expiry"]):
            await self.delete(key)
            return None
        
        path = self._get_path(key)
        if not path.exists():
            await self.delete(key)
            return None
        
        try:
            with open(path, 'rb') as f:
                return pickle.load(f)
        except Exception:
            await self.delete(key)
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        path = self._get_path(key)
        try:
            with open(path, 'wb') as f:
                pickle.dump(value, f)
        except Exception as e:
            logger.error(f"Cache write failed: {e}")
            return
        
        entry = {
            "created": datetime.now().isoformat(),
            "size": path.stat().st_size,
        }
        if ttl:
            entry["expiry"] = (datetime.now() + timedelta(seconds=ttl)).isoformat()
        
        self._index[key] = entry
        self._save_index()
        await self._enforce_size_limit()
    
    async def delete(self, key: str):
        path = self._get_path(key)
        if path.exists():
            path.unlink()
        self._index.pop(key, None)
        self._save_index()
    
    async def clear(self):
        for path in self.cache_dir.glob("*.cache"):
            path.unlink()
        self._index.clear()
        self._save_index()
    
    async def _enforce_size_limit(self):
        total_size = sum(e.get("size", 0) for e in self._index.values())
        if total_size <= self.max_size_bytes:
            return
        
        # Remove oldest entries
        sorted_entries = sorted(
            self._index.items(),
            key=lambda x: x[1].get("created", "")
        )
        
        for key, _ in sorted_entries:
            if total_size <= self.max_size_bytes * 0.8:
                break
            await self.delete(key)
            total_size = sum(e.get("size", 0) for e in self._index.values())


class SharedContext:
    """Shared context for cross-skill communication and state."""
    
    def __init__(
        self,
        cache: Optional[CacheBackend] = None,
        resource_manager: Optional[ResourceManager] = None
    ):
        self.cache = cache or MemoryCache()
        self.resource_manager = resource_manager or ResourceManager()
        self._shared_state: Dict[str, Any] = {}
        self._state_lock = asyncio.Lock()
        self._subscribers: Dict[str, List[Callable]] = {}
        self._execution_history: List[SkillContext] = []
        self._max_history = 1000
    
    async def set_state(self, key: str, value: Any, persist: bool = False):
        """Set shared state value."""
        async with self._state_lock:
            self._shared_state[key] = value
            if persist:
                await self.cache.set(f"state:{key}", value)
            await self._notify_subscribers(key, value)
    
    async def get_state(self, key: str, default: Any = None) -> Any:
        """Get shared state value."""
        async with self._state_lock:
            if key in self._shared_state:
                return self._shared_state[key]
        
        # Try cache
        value = await self.cache.get(f"state:{key}")
        if value is not None:
            async with self._state_lock:
                self._shared_state[key] = value
            return value
        
        return default
    
    async def update_state(self, key: str, updater: Callable[[Any], Any], default: Any = None):
        """Atomically update shared state."""
        async with self._state_lock:
            current = self._shared_state.get(key, default)
            new_value = updater(current)
            self._shared_state[key] = new_value
            await self.cache.set(f"state:{key}", new_value)
            await self._notify_subscribers(key, new_value)
            return new_value
    
    def subscribe(self, key: str, callback: Callable[[Any], Any]):
        """Subscribe to state changes."""
        if key not in self._subscribers:
            self._subscribers[key] = []
        self._subscribers[key].append(callback)
    
    async def _notify_subscribers(self, key: str, value: Any):
        for callback in self._subscribers.get(key, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(value)
                else:
                    callback(value)
            except Exception as e:
                logger.error(f"Subscriber notification failed for {key}: {e}")
    
    def record_execution(self, context: SkillContext):
        """Record skill execution for debugging/analytics."""
        self._execution_history.append(context)
        if len(self._execution_history) > self._max_history:
            self._execution_history = self._execution_history[-self._max_history:]
    
    def get_execution_history(
        self, 
        skill_name: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[SkillContext]:
        """Get execution history with filters."""
        history = self._execution_history
        
        if skill_name:
            history = [h for h in history if h.skill_name == skill_name]
        
        if since:
            history = [
                h for h in history 
                if datetime.fromisoformat(h.started_at) >= since
            ]
        
        return history[-limit:]
    
    async def get_cached(self, key: str, factory: Callable, ttl: Optional[int] = None) -> Any:
        """Get from cache or compute and cache."""
        cached = await self.cache.get(key)
        if cached is not None:
            return cached
        
        if asyncio.iscoroutinefunction(factory):
            value = await factory()
        else:
            value = factory()
        
        await self.cache.set(key, value, ttl)
        return value
    
    async def invalidate_cache(self, pattern: str):
        """Invalidate cache keys matching pattern."""
        # For memory cache, we'd need to track keys
        # For disk cache, we can scan
        if hasattr(self.cache, '_index'):
            keys_to_delete = [k for k in self.cache._index if pattern in k]
            for key in keys_to_delete:
                await self.cache.delete(key)


class ContextManager:
    """Manages context lifecycle for pipeline executions."""
    
    def __init__(self, shared_context: Optional[SharedContext] = None):
        self.shared_context = shared_context or SharedContext()
        self._active_contexts: Dict[str, SkillContext] = {}
        self._context_refs: Dict[str, weakref.ref] = {}
    
    def create_context(
        self,
        skill_name: str,
        config: Dict[str, Any],
        inputs: Optional[Dict[str, Any]] = None
    ) -> SkillContext:
        """Create a new skill execution context."""
        import uuid
        execution_id = f"{skill_name}_{uuid.uuid4().hex[:8]}"
        
        context = SkillContext(
            skill_name=skill_name,
            execution_id=execution_id,
            config=config,
            inputs=inputs or {}
        )
        
        self._active_contexts[execution_id] = context
        self._context_refs[execution_id] = weakref.ref(context)
        
        return context
    
    def complete_context(self, context: SkillContext, outputs: Dict[str, Any], error: Optional[str] = None):
        """Mark context as complete and record."""
        context.complete(outputs, error)
        self.shared_context.record_execution(context)
        self._active_contexts.pop(context.execution_id, None)
        self._context_refs.pop(context.execution_id, None)
    
    def get_active_contexts(self) -> List[SkillContext]:
        """Get all currently active contexts."""
        return list(self._active_contexts.values())
    
    def get_context(self, execution_id: str) -> Optional[SkillContext]:
        """Get context by execution ID."""
        return self._active_contexts.get(execution_id)
    
    async def cleanup(self):
        """Cleanup all resources."""
        await self.shared_context.resource_manager.cleanup()
        await self.shared_context.cache.clear()
        self._active_contexts.clear()
        self._context_refs.clear()