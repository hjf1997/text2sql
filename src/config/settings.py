"""Configuration management for Text-to-SQL Agent.

This module handles loading configuration from YAML files and environment variables.
Environment variables take precedence over YAML configuration.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional
import yaml
from dotenv import load_dotenv


class Settings:
    """Singleton configuration manager for the application."""

    _instance: Optional['Settings'] = None
    _config: Dict[str, Any] = {}

    def __new__(cls):
        """Ensure only one instance of Settings exists."""
        if cls._instance is None:
            cls._instance = super(Settings, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        """Initialize configuration by loading from YAML and environment."""
        # Load environment variables from .env file if it exists
        load_dotenv()

        # Load YAML configuration
        config_path = Path(__file__).parent / "config.yaml"
        if config_path.exists():
            with open(config_path, 'r') as f:
                self._config = yaml.safe_load(f) or {}
        else:
            self._config = {}

        # Override with environment variables
        self._apply_env_overrides()

        # Validate required settings
        self._validate_config()

    def _apply_env_overrides(self) -> None:
        """Override configuration with environment variables."""
        # ConnectChain overrides
        if config_path := os.getenv("CONFIG_PATH"):
            self._config.setdefault("connectchain", {})["config_path"] = config_path

        # BigQuery overrides
        if project_id := os.getenv("GCP_PROJECT_ID"):
            self._config.setdefault("bigquery", {})["project_id"] = project_id
        if dataset := os.getenv("BIGQUERY_DATASET"):
            self._config.setdefault("bigquery", {})["dataset"] = dataset
        if credentials_path := os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            self._config.setdefault("bigquery", {})["credentials_path"] = credentials_path

        # Schema overrides
        if schema_dir := os.getenv("SCHEMA_DIRECTORY"):
            self._config.setdefault("schema", {})["schema_directory"] = schema_dir

    def _validate_config(self) -> None:
        """Validate that required configuration is present."""
        required_fields = [
            ("connectchain.config_path", "CONFIG_PATH"),
            ("bigquery.project_id", "GCP_PROJECT_ID"),
            ("bigquery.dataset", "BIGQUERY_DATASET"),
        ]

        missing = []
        for field_path, env_var in required_fields:
            if not self.get(field_path):
                missing.append(f"{field_path} (env: {env_var})")

        if missing:
            raise ValueError(
                f"Missing required configuration: {', '.join(missing)}. "
                "Please set these in config.yaml or as environment variables."
            )

    def get(self, key_path: str, default: Any = None) -> Any:
        """Get configuration value using dot notation (e.g., 'connectchain.config_path').

        Args:
            key_path: Dot-separated path to configuration value
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        keys = key_path.split('.')
        value = self._config

        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default

        return value

    def get_section(self, section: str) -> Dict[str, Any]:
        """Get an entire configuration section.

        Args:
            section: Top-level section name (e.g., 'connectchain', 'bigquery')

        Returns:
            Dictionary containing the section configuration
        """
        return self._config.get(section, {})

    def set(self, key_path: str, value: Any) -> None:
        """Set configuration value using dot notation.

        Args:
            key_path: Dot-separated path to configuration value
            value: Value to set
        """
        keys = key_path.split('.')
        config = self._config

        for key in keys[:-1]:
            config = config.setdefault(key, {})

        config[keys[-1]] = value

    def reload(self) -> None:
        """Reload configuration from file and environment."""
        self._initialize()

    @property
    def connectchain(self) -> Dict[str, Any]:
        """Get ConnectChain configuration."""
        return self.get_section("connectchain")

    @property
    def bigquery(self) -> Dict[str, Any]:
        """Get BigQuery configuration."""
        return self.get_section("bigquery")

    @property
    def session(self) -> Dict[str, Any]:
        """Get session configuration."""
        return self.get_section("session")

    @property
    def agent(self) -> Dict[str, Any]:
        """Get agent configuration."""
        return self.get_section("agent")

    @property
    def schema(self) -> Dict[str, Any]:
        """Get schema configuration."""
        return self.get_section("schema")

    @property
    def logging(self) -> Dict[str, Any]:
        """Get logging configuration."""
        return self.get_section("logging")


# Global settings instance
settings = Settings()
