from typing import Optional, Dict, Any, Callable

from common.logger import logger
from common.config import settings


class ModelConfigManager:
    """
    Manages model configuration and routing.
    Supports single or multiple model configurations for different intents.
    """

    def __init__(
        self,
        model_config: Optional[Dict[str, Any]] = None,
        create_client: Optional[Callable] = None,
    ):
        self._model_config = model_config or {}
        self._create_client = create_client

    def get_model_config(self, intent: str = "default") -> Dict[str, Any]:
        """
        Get model configuration for a given intent.
        
        Args:
            intent: The intent type ('planning', 'default', 'insight')
        
        Returns:
            Model configuration dict
        """
        if intent in self._model_config:
            return self._model_config[intent]
        
        if "default" in self._model_config:
            return self._model_config["default"]
        
        return self._model_config

    def get_upload_test_server_url(self) -> Optional[str]:
        """Get upload server URL if configured"""
        return self._model_config.get("upload_server_url")

    def throw_error_if_non_vl_model(self) -> None:
        """Throw error if a vision-language model is required but not configured"""
        model_family = self._model_config.get("model_family")
        if not model_family:
            logger.debug("No model_family configured, this may cause issues for non-web interfaces")


# Global model config manager instance
global_model_config_manager = ModelConfigManager()
