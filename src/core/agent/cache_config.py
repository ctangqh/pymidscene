from typing import Optional, Any, Literal
from common.exceptions import ConfigError

CacheStrategy = Literal["read-only", "read-write", "write-only"]

VALID_CACHE_STRATEGIES = ("read-only", "read-write", "write-only")

def validate_agent_cache_input(cache: Optional[Any]) -> None:
    """
    Validate agent cache configuration.
    Raises ConfigError if validation fails.
    
    Port of TS validateAgentCacheInput.
    """
    # Agent requires explicit IDs - don't allow auto-generation
    if cache is True:
        raise ConfigError(
            'cache: True requires an explicit cache ID. Please provide:\n'
            'Example: cache={"id": "my-cache-id"}'
        )
    
    if not cache or not isinstance(cache, dict):
        return
    
    if not cache.get("id"):
        raise ConfigError(
            'cache configuration requires an explicit id.\n'
            'Example: cache={"id": "my-cache-id"}'
        )
    
    cache_dir = cache.get("cache_dir")
    if cache_dir is not None and (not isinstance(cache_dir, str) or not cache_dir.strip()):
        raise ConfigError(
            'cache.cache_dir must be a non-empty string when provided.\n'
            'Example: cache={"id": "my-cache-id", "cache_dir": "./my-cache-dir"}'
        )
    
    strategy = cache.get("strategy")
    if strategy is not None:
        if not isinstance(strategy, str):
            raise ConfigError(
                f'cache.strategy must be a string when provided, but received type {type(strategy).__name__}'
            )
        if strategy not in VALID_CACHE_STRATEGIES:
            strategies_str = ', '.join(f'"{s}"' for s in VALID_CACHE_STRATEGIES)
            raise ConfigError(
                f'cache.strategy must be one of {strategies_str}, but received "{strategy}"'
            )
