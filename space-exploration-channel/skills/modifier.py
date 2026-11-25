"""
Skill Modifiers - Composable modifiers for skill behavior.
Enables cross-cutting concerns: logging, caching, retry, timeout, metrics, etc.
"""

import asyncio
import logging
import time
import functools
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar, Generic
from contextlib import asynccontextmanager


logger = logging.getLogger(__name__)

T = TypeVar('T')
R = TypeVar('R')


class ModifierType(Enum):
    """Types of modifiers."""
    LOGGING = "logging"
    CACHING = "caching"
    RETRY = "retry"
    TIMEOUT = "timeout"
    METRICS = "metrics"
    VALIDATION = "validation"
    TRANSFORM = "transform"
    CONDITIONAL = "conditional"
    RATE_LIMIT = "rate_limit"
    CIRCUIT_BREAKER = "circuit_breaker"


@dataclass
class ModifierConfig:
    """Configuration for a modifier."""
    modifier_type: ModifierType
    enabled: bool = True
    priority: int = 0  # Lower runs first
    params: Dict[str, Any] = field(default_factory=dict)


class SkillModifier(ABC, Generic[T, R]):
    """Base class for skill modifiers."""
    
    def __init__(self, config: ModifierConfig):
        self.config = config
        self.logger = logging.getLogger(f"modifier.{config.modifier_type.value}")
    
    @abstractmethod
    async def apply(self, func: Callable[..., T], *args, **kwargs) -> R:
        """Apply modifier to function execution."""
        pass
    
    def can_apply(self, skill_name: str, context: Dict[str, Any]) -> bool:
        """Check if modifier should apply to this skill/context."""
        return self.config.enabled


class ModifierChain:
    """Chain of modifiers applied in priority order."""
    
    def __init__(self):
        self._modifiers: List[SkillModifier] = []
    
    def add(self, modifier: SkillModifier) -> "ModifierChain":
        self._modifiers.append(modifier)
        self._modifiers.sort(key=lambda m: m.config.priority)
        return self
    
    def remove(self, modifier_type: ModifierType) -> "ModifierChain":
        self._modifiers = [m for m in self._modifiers if m.config.modifier_type != modifier_type]
        return self
    
    async def execute(self, func: Callable[..., T], *args, **kwargs) -> R:
        """Execute function through all modifiers."""
        if not self._modifiers:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            return func(*args, **kwargs)
        
        # Build nested wrapper
        async def execute_chain(index: int, *a, **kw) -> R:
            if index >= len(self._modifiers):
                if asyncio.iscoroutinefunction(func):
                    return await func(*a, **kw)
                return func(*a, **kw)
            
            modifier = self._modifiers[index]
            
            # Create next function in chain
            async def next_func(*na, **nkw):
                return await execute_chain(index + 1, *na, **nkw)
            
            return await modifier.apply(next_func, *a, **kw)
        
        return await execute_chain(0, *args, **kwargs)
    
    def get_modifiers(self) -> List[SkillModifier]:
        return self._modifiers.copy()


# ============================================================================
# Built-in Modifiers
# ============================================================================

class LoggingModifier(SkillModifier):
    """Logs skill execution with timing and context."""
    
    async def apply(self, func: Callable, *args, **kwargs) -> Any:
        skill_name = kwargs.get('skill_name', 'unknown')
        start = time.perf_counter()
        
        self.logger.info(f"[{skill_name}] Starting execution")
        
        try:
            result = await func(*args, **kwargs)
            duration = time.perf_counter() - start
            self.logger.info(f"[{skill_name}] Completed in {duration:.3f}s")
            return result
        except Exception as e:
            duration = time.perf_counter() - start
            self.logger.error(f"[{skill_name}] Failed after {duration:.3f}s: {e}")
            raise


class CachingModifier(SkillModifier):
    """Caches skill results based on input hash."""
    
    def __init__(self, config: ModifierConfig, cache_backend: Any):
        super().__init__(config)
        self.cache = cache_backend
        self.ttl = config.params.get('ttl', 3600)
        self.key_prefix = config.params.get('key_prefix', 'skill_cache')
    
    async def apply(self, func: Callable, *args, **kwargs) -> Any:
        # Generate cache key from inputs
        import hashlib
        import json
        
        cache_inputs = {
            'args': args,
            'kwargs': {k: v for k, v in kwargs.items() if k != 'context'}
        }
        key_data = json.dumps(cache_inputs, sort_keys=True, default=str)
        cache_key = f"{self.key_prefix}:{hashlib.sha256(key_data.encode()).hexdigest()[:16]}"
        
        # Try cache
        cached = await self.cache.get(cache_key)
        if cached is not None:
            self.logger.debug(f"Cache hit: {cache_key}")
            return cached
        
        # Execute and cache
        result = await func(*args, **kwargs)
        await self.cache.set(cache_key, result, self.ttl)
        self.logger.debug(f"Cache set: {cache_key}")
        return result


class RetryModifier(SkillModifier):
    """Retries failed executions with exponential backoff."""
    
    def __init__(self, config: ModifierConfig):
        super().__init__(config)
        self.max_attempts = config.params.get('max_attempts', 3)
        self.base_delay = config.params.get('base_delay', 1.0)
        self.max_delay = config.params.get('max_delay', 60.0)
        self.exponential_base = config.params.get('exponential_base', 2.0)
        self.retry_exceptions = config.params.get('retry_exceptions', (Exception,))
    
    async def apply(self, func: Callable, *args, **kwargs) -> Any:
        last_exception = None
        
        for attempt in range(1, self.max_attempts + 1):
            try:
                return await func(*args, **kwargs)
            except self.retry_exceptions as e:
                last_exception = e
                if attempt == self.max_attempts:
                    break
                
                delay = min(
                    self.base_delay * (self.exponential_base ** (attempt - 1)),
                    self.max_delay
                )
                self.logger.warning(
                    f"Attempt {attempt}/{self.max_attempts} failed: {e}. "
                    f"Retrying in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)
        
        raise last_exception


class TimeoutModifier(SkillModifier):
    """Enforces execution timeout."""
    
    def __init__(self, config: ModifierConfig):
        super().__init__(config)
        self.timeout = config.params.get('timeout', 300.0)  # 5 minutes default
    
    async def apply(self, func: Callable, *args, **kwargs) -> Any:
        try:
            return await asyncio.wait_for(func(*args, **kwargs), timeout=self.timeout)
        except asyncio.TimeoutError:
            self.logger.error(f"Execution timed out after {self.timeout}s")
            raise


class MetricsModifier(SkillModifier):
    """Collects execution metrics."""
    
    def __init__(self, config: ModifierConfig, metrics_collector: Any = None):
        super().__init__(config)
        self.collector = metrics_collector
        self.metrics: Dict[str, List[Dict]] = {}
    
    async def apply(self, func: Callable, *args, **kwargs) -> Any:
        skill_name = kwargs.get('skill_name', 'unknown')
        start = time.perf_counter()
        success = False
        error = None
        
        try:
            result = await func(*args, **kwargs)
            success = True
            return result
        except Exception as e:
            error = str(e)
            raise
        finally:
            duration = time.perf_counter() - start
            metric = {
                'skill': skill_name,
                'duration': duration,
                'success': success,
                'error': error,
                'timestamp': datetime.now().isoformat()
            }
            
            if skill_name not in self.metrics:
                self.metrics[skill_name] = []
            self.metrics[skill_name].append(metric)
            
            if self.collector:
                await self.collector.record(metric)


class ValidationModifier(SkillModifier):
    """Validates inputs and outputs against schemas."""
    
    def __init__(self, config: ModifierConfig):
        super().__init__(config)
        self.input_schema = config.params.get('input_schema')
        self.output_schema = config.params.get('output_schema')
        self.strict = config.params.get('strict', True)
    
    async def apply(self, func: Callable, *args, **kwargs) -> Any:
        # Validate inputs
        if self.input_schema:
            self._validate(kwargs, self.input_schema, "input")
        
        result = await func(*args, **kwargs)
        
        # Validate outputs
        if self.output_schema:
            self._validate(result, self.output_schema, "output")
        
        return result
    
    def _validate(self, data: Dict, schema: Dict, stage: str):
        """Simple schema validation."""
        for field, rules in schema.items():
            if field not in data:
                if rules.get('required', False):
                    raise ValueError(f"Missing required {stage} field: {field}")
                continue
            
            value = data[field]
            if 'type' in rules:
                expected = rules['type']
                if not isinstance(value, expected):
                    raise TypeError(
                        f"{stage} field '{field}' expected {expected.__name__}, "
                        f"got {type(value).__name__}"
                    )
            
            if 'enum' in rules and value not in rules['enum']:
                raise ValueError(f"{stage} field '{field}' must be one of {rules['enum']}")


class TransformModifier(SkillModifier):
    """Transforms inputs before execution and outputs after."""
    
    def __init__(self, config: ModifierConfig):
        super().__init__(config)
        self.input_transform = config.params.get('input_transform')
        self.output_transform = config.params.get('output_transform')
    
    async def apply(self, func: Callable, *args, **kwargs) -> Any:
        # Transform inputs
        if self.input_transform:
            if asyncio.iscoroutinefunction(self.input_transform):
                kwargs = await self.input_transform(kwargs)
            else:
                kwargs = self.input_transform(kwargs)
        
        result = await func(*args, **kwargs)
        
        # Transform outputs
        if self.output_transform:
            if asyncio.iscoroutinefunction(self.output_transform):
                result = await self.output_transform(result)
            else:
                result = self.output_transform(result)
        
        return result


class ConditionalModifier(SkillModifier):
    """Conditionally executes skill based on predicate."""
    
    def __init__(self, config: ModifierConfig):
        super().__init__(config)
        self.predicate = config.params.get('predicate')
        self.fallback = config.params.get('fallback')
    
    async def apply(self, func: Callable, *args, **kwargs) -> Any:
        if self.predicate:
            should_execute = self.predicate(kwargs)
            if asyncio.iscoroutinefunction(self.predicate):
                should_execute = await should_execute(kwargs)
            
            if not should_execute:
                self.logger.info("Condition not met, skipping execution")
                if self.fallback:
                    if asyncio.iscoroutinefunction(self.fallback):
                        return await self.fallback(*args, **kwargs)
                    return self.fallback(*args, **kwargs)
                return None
        
        return await func(*args, **kwargs)


class RateLimitModifier(SkillModifier):
    """Rate limits skill executions."""
    
    def __init__(self, config: ModifierConfig, resource_manager: Any = None):
        super().__init__(config)
        self.resource_manager = resource_manager
        self.resource_name = config.params.get('resource', 'default')
        self.cost = config.params.get('cost', 1)
    
    async def apply(self, func: Callable, *args, **kwargs) -> Any:
        if self.resource_manager:
            allowed = await self.resource_manager.check_quota(self.resource_name, self.cost)
            if not allowed:
                remaining = self.resource_manager.get_quota_remaining(self.resource_name)
                raise RuntimeError(f"Rate limit exceeded for {self.resource_name}. Remaining: {remaining}")
        
        return await func(*args, **kwargs)


class CircuitBreakerState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerModifier(SkillModifier):
    """Circuit breaker pattern for fault tolerance."""
    
    def __init__(self, config: ModifierConfig):
        super().__init__(config)
        self.failure_threshold = config.params.get('failure_threshold', 5)
        self.recovery_timeout = config.params.get('recovery_timeout', 60.0)
        self.success_threshold = config.params.get('success_threshold', 2)
        
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()
    
    async def apply(self, func: Callable, *args, **kwargs) -> Any:
        async with self._lock:
            if self._state == CircuitBreakerState.OPEN:
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitBreakerState.HALF_OPEN
                    self._success_count = 0
                    self.logger.info("Circuit breaker entering HALF_OPEN state")
                else:
                    raise RuntimeError("Circuit breaker is OPEN")
        
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise
    
    async def _on_success(self):
        async with self._lock:
            self._failure_count = 0
            
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitBreakerState.CLOSED
                    self.logger.info("Circuit breaker CLOSED")
    
    async def _on_failure(self):
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            self._success_count = 0
            
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._state = CircuitBreakerState.OPEN
                self.logger.warning("Circuit breaker OPEN after half-open failure")
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitBreakerState.OPEN
                self.logger.warning(f"Circuit breaker OPEN after {self._failure_count} failures")


# ============================================================================
# Modifier Factory
# ============================================================================

class ModifierFactory:
    """Factory for creating standard modifier chains."""
    
    def __init__(
        self,
        cache_backend: Any = None,
        resource_manager: Any = None,
        metrics_collector: Any = None
    ):
        self.cache_backend = cache_backend
        self.resource_manager = resource_manager
        self.metrics_collector = metrics_collector
    
    def create_standard_chain(
        self,
        skill_name: str,
        enable_cache: bool = True,
        enable_retry: bool = True,
        enable_timeout: bool = True,
        enable_metrics: bool = True,
        custom_modifiers: Optional[List[SkillModifier]] = None
    ) -> ModifierChain:
        """Create a standard modifier chain for a skill."""
        chain = ModifierChain()
        
        # Order matters: logging -> rate_limit -> circuit_breaker -> timeout -> retry -> cache -> metrics
        
        chain.add(LoggingModifier(ModifierConfig(ModifierType.LOGGING, priority=10)))
        
        if self.resource_manager:
            chain.add(RateLimitModifier(
                ModifierConfig(ModifierType.RATE_LIMIT, priority=20),
                self.resource_manager
            ))
        
        chain.add(CircuitBreakerModifier(
            ModifierConfig(ModifierType.CIRCUIT_BREAKER, priority=30)
        ))
        
        if enable_timeout:
            chain.add(TimeoutModifier(
                ModifierConfig(ModifierType.TIMEOUT, priority=40, params={'timeout': 300})
            ))
        
        if enable_retry:
            chain.add(RetryModifier(
                ModifierConfig(ModifierType.RETRY, priority=50, params={
                    'max_attempts': 3,
                    'base_delay': 1.0,
                    'retry_exceptions': (Exception,)
                })
            ))
        
        if enable_cache and self.cache_backend:
            chain.add(CachingModifier(
                ModifierConfig(ModifierType.CACHING, priority=60, params={
                    'ttl': 3600,
                    'key_prefix': f'skill_cache:{skill_name}'
                }),
                self.cache_backend
            ))
        
        if enable_metrics:
            chain.add(MetricsModifier(
                ModifierConfig(ModifierType.METRICS, priority=70),
                self.metrics_collector
            ))
        
        if custom_modifiers:
            for mod in custom_modifiers:
                chain.add(mod)
        
        return chain
    
    def create_research_chain(self) -> ModifierChain:
        return self.create_standard_chain(
            'research',
            enable_cache=True,
            enable_retry=True,
            enable_timeout=True,
            enable_metrics=True
        )
    
    def create_script_chain(self) -> ModifierChain:
        return self.create_standard_chain(
            'script',
            enable_cache=False,  # Scripts should be unique
            enable_retry=True,
            enable_timeout=True,
            enable_metrics=True
        )
    
    def create_vfx_chain(self) -> ModifierChain:
        return self.create_standard_chain(
            'vfx',
            enable_cache=True,
            enable_retry=True,
            enable_timeout=True,  # Longer timeout for rendering
            enable_metrics=True
        )
    
    def create_voice_chain(self) -> ModifierChain:
        return self.create_standard_chain(
            'voice',
            enable_cache=True,  # Cache TTS for repeated phrases
            enable_retry=True,
            enable_timeout=True,
            enable_metrics=True
        )
    
    def create_upload_chain(self) -> ModifierChain:
        return self.create_standard_chain(
            'upload',
            enable_cache=False,
            enable_retry=True,
            enable_timeout=True,
            enable_metrics=True
        )


def with_modifiers(*modifiers: SkillModifier):
    """Decorator to apply modifiers to a skill method."""
    def decorator(func: Callable):
        chain = ModifierChain()
        for mod in modifiers:
            chain.add(mod)
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await chain.execute(func, *args, **kwargs)
        return wrapper
    return decorator