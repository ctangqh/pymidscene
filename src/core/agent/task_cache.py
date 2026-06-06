import os
import json
import hashlib
import time
from typing import Optional, List, Dict, Any, Tuple, Callable, Union
from pathlib import Path

import yaml  # pyyaml

from ..types import (
    PlanningCache, LocateCache, ElementCacheFeature,
    CacheFileContent, CacheConfig
)
from common.logger import logger
from common.exceptions import ConfigError, TaskError

# Version compatibility
LOWEST_SUPPORTED_MIDSCENE_VERSION = "0.16.10"
CACHE_FILE_EXT = ".cache.yaml"
DEFAULT_CACHE_MAX_FILENAME_LENGTH = 200


def _get_midscene_version() -> str:
    """Get current pymidscene version"""
    try:
        from importlib.metadata import version
        return version("pymidscene")
    except Exception:
        return "0.1.0"


def _generate_hash_id(data: str) -> str:
    """Generate a short hash ID from string data"""
    return hashlib.sha256(data.encode()).hexdigest()[:12]


def _replace_illegal_path_chars(name: str) -> str:
    """Replace characters that are illegal in file paths"""
    import re
    # Replace characters not safe for filenames
    result = re.sub(r'[<>:"/\\|?*\s]', '_', name)
    return result


def _get_midscene_run_sub_dir(subdir: str) -> str:
    """Get or create a subdirectory under the midscene run directory"""
    base_dir = Path(".midscene")
    target = base_dir / subdir
    target.mkdir(parents=True, exist_ok=True)
    return str(target)


class MatchCacheResult:
    """Result of a cache match operation"""
    def __init__(self, cache_content: Union[PlanningCache, LocateCache], 
                 cache_usable: bool, update_fn: Callable):
        self.cache_content = cache_content
        self.cache_usable = cache_usable
        self.update_fn = update_fn  # Callable that takes a callback to update cache


class TaskCache:
    """
    Task cache for storing and retrieving plan and locate results.
    Persists cache to YAML files.
    
    Port of TS TaskCache class.
    """
    
    def __init__(
        self,
        cache_id: str,
        is_cache_result_used: bool,
        cache_file_path: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ):
        options = options or {}
        
        if not cache_id:
            raise ValueError("cacheId is required")
        
        cache_dir = options.get("cache_dir")
        if cache_dir is not None and (not isinstance(cache_dir, str) or not cache_dir.strip()):
            raise ValueError("cache_dir must be a non-empty string when provided")
        
        cache_dir = cache_dir.strip() if cache_dir else None
        
        # Sanitize cache ID for use as filename
        safe_cache_id = _replace_illegal_path_chars(cache_id)
        if len(safe_cache_id.encode('utf-8')) > DEFAULT_CACHE_MAX_FILENAME_LENGTH:
            prefix = safe_cache_id[:32]
            hash_id = _generate_hash_id(safe_cache_id)
            safe_cache_id = f"{prefix}-{hash_id}"
        
        self.cache_id = safe_cache_id
        self.cache_file_path = cache_file_path or os.path.join(
            cache_dir or _get_midscene_run_sub_dir("cache"),
            f"{self.cache_id}{CACHE_FILE_EXT}"
        )
        
        read_only_mode = bool(options.get("read_only", False))
        write_only_mode = bool(options.get("write_only", False))
        
        if read_only_mode and write_only_mode:
            raise ValueError("TaskCache cannot be both read-only and write-only")
        
        self.is_cache_result_used = False if write_only_mode else is_cache_result_used
        self.read_only_mode = read_only_mode
        self.write_only_mode = write_only_mode
        
        # Track matched cache indices
        self._matched_cache_indices: set = set()
        
        # Per "type:promptStr", indices of consumed entries
        self._consumed_cache_indices: Dict[str, List[int]] = {}
        
        # Per "type:promptStr", indices of stale entries  
        self._stale_cache_indices: Dict[str, List[int]] = {}
        
        # Load or initialize cache content
        cache_content = None
        if self.cache_file_path and not self.write_only_mode:
            cache_content = self._load_cache_from_file()
        
        if not cache_content:
            cache_content = {
                "midscene_version": _get_midscene_version(),
                "cache_id": self.cache_id,
                "caches": [],
            }
        
        self.cache = cache_content
        self.cache_original_length = len(self.cache["caches"]) if self.is_cache_result_used else 0
    
    def _prompt_key(self, prompt: Any) -> str:
        """Turn a prompt into a stable string key"""
        if isinstance(prompt, str):
            return prompt
        return json.dumps(prompt, sort_keys=True, default=str)
    
    def match_cache(self, prompt: Any, cache_type: str) -> Optional[MatchCacheResult]:
        """
        Match a cache entry by type and prompt.
        Returns MatchCacheResult if found, None otherwise.
        """
        if not self.is_cache_result_used:
            return None
        
        prompt_str = self._prompt_key(prompt)
        
        for i in range(self.cache_original_length):
            item = self.cache["caches"][i]
            key = f"{cache_type}:{prompt_str}:{i}"
            
            if (item.get("type") == cache_type and 
                self._prompt_key(item.get("prompt", "")) == prompt_str and
                key not in self._matched_cache_indices):
                
                # Mark as used
                self._matched_cache_indices.add(key)
                
                # Track consumed index
                consume_key = f"{cache_type}:{prompt_str}"
                consumed = self._consumed_cache_indices.get(consume_key, [])
                consumed.append(i)
                self._consumed_cache_indices[consume_key] = consumed
                
                logger.debug(f"cache found, type: {cache_type}, prompt: {prompt_str}, index: {i}")
                
                # Create Pydantic model from dict
                if cache_type == "plan":
                    cache_content = PlanningCache(**item)
                else:
                    cache_content = LocateCache(**item)
                
                return MatchCacheResult(
                    cache_content=cache_content,
                    cache_usable=True,
                    update_fn=lambda cb, idx=i, itm=item: self._update_cache_entry(cb, itm),
                )
        
        logger.debug(f"no unused cache found, type: {cache_type}, prompt: {prompt_str}")
        return None
    
    def _update_cache_entry(self, cb: Callable, item: dict) -> None:
        """Update a cache entry in place using callback"""
        cb(item)
        
        if self.read_only_mode:
            logger.debug("read-only mode, cache updated in memory but not flushed to file")
            return
        
        logger.debug("cache updated, will flush to file")
        self.flush_cache_to_file()
    
    def match_plan_cache(self, prompt: Any) -> Optional[MatchCacheResult]:
        """Match a plan cache entry"""
        result = self.match_cache(prompt, "plan")
        if not result:
            return None
        
        # Guard against stale cache with empty yamlWorkflow
        assert isinstance(result.cache_content, PlanningCache)
        yaml_workflow = result.cache_content.yaml_workflow
        if not yaml_workflow or not yaml_workflow.strip():
            logger.debug("plan cache matched but yamlWorkflow is empty, treating as cache miss")
            return MatchCacheResult(
                cache_content=result.cache_content,
                cache_usable=False,
                update_fn=result.update_fn,
            )
        
        # Validate YAML structure
        try:
            parsed = yaml.safe_load(yaml_workflow)
            has_non_empty_flow = any(
                isinstance(task.get("flow"), list) and len(task.get("flow", [])) > 0
                for task in (parsed.get("tasks", []) if isinstance(parsed, dict) else [])
            )
            if not has_non_empty_flow:
                logger.debug("plan cache matched but flow is empty, treating as cache miss")
                return MatchCacheResult(
                    cache_content=result.cache_content,
                    cache_usable=False,
                    update_fn=result.update_fn,
                )
        except Exception:
            logger.debug("plan cache matched but yamlWorkflow is invalid, treating as cache miss")
            return MatchCacheResult(
                cache_content=result.cache_content,
                cache_usable=False,
                update_fn=result.update_fn,
            )
        
        return result
    
    def match_locate_cache(self, prompt: Any) -> Optional[MatchCacheResult]:
        """Match a locate cache entry"""
        return self.match_cache(prompt, "locate")
    
    def append_cache(self, cache_entry: Union[PlanningCache, LocateCache]) -> None:
        """Append a new cache entry"""
        logger.debug(f"will append cache: type={cache_entry.type}")
        self.cache["caches"].append(cache_entry.model_dump())
        
        if self.read_only_mode:
            logger.debug("read-only mode, cache appended to memory but not flushed to file")
            return
        
        self.flush_cache_to_file()
    
    def update_or_append_cache_record(
        self,
        new_record: Union[PlanningCache, LocateCache],
        cached_record: Optional[MatchCacheResult] = None,
    ) -> None:
        """Update an existing cache record or append a new one"""
        if cached_record:
            # Update existing record
            def update_fn(item: dict):
                self._apply_record_into(item, new_record)
            cached_record.update_fn(update_fn)
        else:
            # Check for stale entries to replace
            consume_key = f"{new_record.type}:{self._prompt_key(new_record.prompt)}"
            stale_indices = self._stale_cache_indices.get(consume_key, [])
            stale_index = stale_indices.pop() if stale_indices else None
            
            if stale_index is not None and stale_index < len(self.cache["caches"]):
                logger.debug(f"replacing stale cache entry, type: {new_record.type}, index: {stale_index}")
                self._replace_cache_record(stale_index, new_record)
            else:
                self.append_cache(new_record)
    
    def mark_locate_cache_stale(self, prompt: Any) -> None:
        """
        Mark the most recently consumed locate cache entry as stale.
        Called when an action that used the cache-hit element failed.
        """
        consume_key = f"locate:{self._prompt_key(prompt)}"
        indices = self._consumed_cache_indices.get(consume_key, [])
        if not indices:
            return
        
        index = indices.pop()
        stale = self._stale_cache_indices.get(consume_key, [])
        stale.append(index)
        self._stale_cache_indices[consume_key] = stale
        logger.debug(f"marked locate cache entry as stale, prompt: {prompt}, index: {index}")
    
    def _apply_record_into(self, target: dict, new_record: Union[PlanningCache, LocateCache]) -> None:
        """Copy mutable payload from new_record into target dict"""
        if new_record.type == "plan":
            target["yaml_workflow"] = new_record.yaml_workflow
        else:
            target["cache"] = new_record.cache.model_dump() if new_record.cache else None
            target.pop("xpaths", None)
    
    def _replace_cache_record(self, index: int, new_record: Union[PlanningCache, LocateCache]) -> None:
        """Replace a cache record at the given index"""
        target = self.cache["caches"][index]
        if target.get("type") != new_record.type:
            raise ValueError(f"cache record type mismatch on replace: expected {new_record.type}, got {target.get('type')}")
        
        self._apply_record_into(target, new_record)
        
        if self.read_only_mode:
            logger.debug("read-only mode, cache replaced in memory but not flushed to file")
            return
        
        self.flush_cache_to_file()
    
    def flush_cache_to_file(self, options: Optional[Dict[str, Any]] = None) -> None:
        """Write cache content to YAML file"""
        version = _get_midscene_version()
        if not version:
            logger.debug("no version info, will not write cache to file")
            return
        
        if not self.cache_file_path:
            logger.debug("no cache file path, will not write cache to file")
            return
        
        # Clean unused caches if requested
        if options and options.get("clean_unused"):
            if self.is_cache_result_used:
                original_length = len(self.cache["caches"])
                used_indices = set()
                for key in self._matched_cache_indices:
                    parts = key.split(":")
                    try:
                        idx = int(parts[-1])
                        used_indices.add(idx)
                    except ValueError:
                        pass
                
                self.cache["caches"] = [
                    entry for i, entry in enumerate(self.cache["caches"])
                    if i in used_indices or i >= self.cache_original_length
                ]
                removed = original_length - len(self.cache["caches"])
                if removed > 0:
                    logger.debug(f"cleaned {removed} unused cache record(s)")
        
        try:
            # Ensure directory exists
            dir_path = os.path.dirname(self.cache_file_path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            
            # Sort caches: plan entries before locate entries
            sorted_caches = sorted(
                self.cache["caches"],
                key=lambda x: (0 if x.get("type") == "plan" else 1)
            )
            
            cache_to_write = {
                "midscene_version": version,
                "cache_id": self.cache["cache_id"],
                "caches": sorted_caches,
            }
            
            yaml_data = yaml.dump(cache_to_write, allow_unicode=True, default_flow_style=False)
            with open(self.cache_file_path, 'w', encoding='utf-8') as f:
                f.write(yaml_data)
            
            logger.debug(f"cache flushed to file: {self.cache_file_path}")
        except Exception as e:
            logger.warning(f"write cache to file failed, path: {self.cache_file_path}, error: {e}")
    
    def _load_cache_from_file(self) -> Optional[Dict[str, Any]]:
        """Load cache content from YAML file"""
        if not self.cache_file_path:
            return None
        
        if not os.path.exists(self.cache_file_path):
            logger.debug(f"no cache file found, path: {self.cache_file_path}")
            return None
        
        # Check for old JSON cache format
        json_cache_file = self.cache_file_path.replace(CACHE_FILE_EXT, ".json")
        if os.path.exists(json_cache_file) and self.is_cache_result_used:
            logger.warning(
                f"An outdated cache file from an earlier version has been detected. "
                f"Please delete the old file: {json_cache_file}"
            )
            return None
        
        try:
            with open(self.cache_file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            if not isinstance(data, dict):
                logger.debug("cache file content is not a dict")
                return None
            
            version = data.get("midscene_version", "")
            current_version = _get_midscene_version()
            
            if not current_version:
                logger.debug("no version info, will not read cache from file")
                return None
            
            # Version compatibility check (basic - compare first two segments)
            if version and not version.startswith("0.1"):  # Our version is 0.1.x
                try:
                    from packaging.version import Version
                    if Version(version) < Version(LOWEST_SUPPORTED_MIDSCENE_VERSION):
                        logger.warning(
                            f"Old cache version detected ({version}). "
                            f"Please delete existing cache and rebuild it. "
                            f"Cache file: {self.cache_file_path}"
                        )
                        return None
                except ImportError:
                    # packaging not available, skip version check
                    pass
            
            logger.debug(
                f"cache loaded from file, path: {self.cache_file_path}, "
                f"cache version: {version}, record length: {len(data.get('caches', []))}"
            )
            
            # Update version to current
            data["midscene_version"] = current_version
            return data
            
        except Exception as e:
            logger.debug(f"cache file exists but load failed, path: {self.cache_file_path}, error: {e}")
            return None
