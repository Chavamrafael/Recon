"""Configuration management."""

import os
import yaml
from typing import Optional


class PipelineConfig:
    """Load and manage pipeline configuration from YAML file."""
    
    def __init__(self, config_file: Optional[str] = None):
        self.global_daily = 1.0
        self.global_weekly = 5.0
        self.index_overrides = {}
        
        if config_file and os.path.exists(config_file):
            self._load_config(config_file)
        elif os.path.exists("config.yaml"):
            self._load_config("config.yaml")
    
    def _load_config(self, file_path: str):
        """Load configuration from YAML file."""
        try:
            with open(file_path, 'r') as f:
                config = yaml.safe_load(f)
                
            if config and 'global' in config:
                self.global_daily = config['global'].get('daily_threshold', 1.0)
                self.global_weekly = config['global'].get('weekly_threshold', 5.0)
            
            if config and 'indexes' in config:
                for index, settings in config['indexes'].items():
                    if settings:
                        self.index_overrides[index] = {
                            'daily': settings.get('daily_threshold'),
                            'weekly': settings.get('weekly_threshold')
                        }
        except Exception as e:
            print(f"Warning: Failed to load config file {file_path}: {e}")
