"""
SKU Profile Manager Service.
Handles loading, saving, and validating production configuration JSON profiles
to prevent operator setup errors on the manufacturing line.
"""

import json
import os
from typing import Dict, Any, List, Optional
from src.common import get_logger

logger = get_logger("ProfileManager")

DEFAULT_PROFILES_DIR = os.path.join(os.getcwd(), "profiles")


class SKUProfile:
    """
    Data model representing a locked production SKU configuration profile.
    """

    def __init__(
        self,
        name: str = "STM32-Generic-SKU",
        file_path: str = "",
        base_address: int = 0x08000000,
        clock_freq: int = 1000000,
        connect_mode: str = "under-reset",
        verify_enabled: bool = True,
        enable_provisioning: bool = False,
        serial_address: int = 0x0801FC00,
    ):
        self.name = name
        self.file_path = file_path
        self.base_address = base_address
        self.clock_freq = clock_freq
        self.connect_mode = connect_mode
        self.verify_enabled = verify_enabled
        self.enable_provisioning = enable_provisioning
        self.serial_address = serial_address

    def to_dict(self) -> Dict[str, Any]:
        """Serializes profile properties to a dictionary."""
        return {
            "name": self.name,
            "file_path": self.file_path,
            "base_address": hex(self.base_address),
            "clock_freq": self.clock_freq,
            "connect_mode": self.connect_mode,
            "verify_enabled": self.verify_enabled,
            "enable_provisioning": self.enable_provisioning,
            "serial_address": hex(self.serial_address),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SKUProfile":
        """Deserializes dictionary data into an SKUProfile instance."""
        return cls(
            name=data.get("name", "Unnamed-SKU"),
            file_path=data.get("file_path", ""),
            base_address=int(str(data.get("base_address", "0x08000000")), 16),
            clock_freq=int(data.get("clock_freq", 1000000)),
            connect_mode=data.get("connect_mode", "under-reset"),
            verify_enabled=bool(data.get("verify_enabled", True)),
            enable_provisioning=bool(data.get("enable_provisioning", False)),
            serial_address=int(
                str(data.get("serial_address", "0x0801FC00")), 16),
        )


class ProfileManager:
    """
    Manages persistence and retrieval of SKU profiles on disk.
    """

    def __init__(self, profiles_dir: str = DEFAULT_PROFILES_DIR):
        self.profiles_dir = profiles_dir
        self._ensure_profiles_directory()

    def _ensure_profiles_directory(self) -> None:
        if not os.path.exists(self.profiles_dir):
            os.makedirs(self.profiles_dir, exist_ok=True)
            default_profile = SKUProfile(
                name="STM32F4-Factory-Default",
                base_address=0x08000000,
                clock_freq=1000000,
            )
            self.save_profile(default_profile)
            logger.info(
                "Created default profile directory and baseline SKU profile.")

    def list_profile_names(self) -> List[str]:
        """Returns a list of all saved SKU profile names."""
        profiles = []
        if not os.path.exists(self.profiles_dir):
            return profiles

        for filename in os.listdir(self.profiles_dir):
            if filename.endswith(".json"):
                profiles.append(os.path.splitext(filename)[0])
        return sorted(profiles)

    def save_profile(self, profile: SKUProfile) -> bool:
        """Saves an SKU profile to a JSON file."""
        try:
            filename = f"{profile.name}.json"
            file_path = os.path.join(self.profiles_dir, filename)
            with open(file_path, "w", encoding="utf-8") as file:
                json.dump(profile.to_dict(), file, indent=4)
            logger.info(f"Successfully saved SKU profile: {profile.name}")
            return True
        except Exception as exc:
            logger.error(f"Failed to save SKU profile '{profile.name}': {exc}")
            return False

    def load_profile(self, profile_name: str) -> Optional[SKUProfile]:
        """Loads an SKU profile from disk by name."""
        try:
            file_path = os.path.join(self.profiles_dir, f"{profile_name}.json")
            if not os.path.exists(file_path):
                logger.warning(f"SKU profile '{profile_name}' not found.")
                return None

            with open(file_path, "r", encoding="utf-8") as file:
                data = json.load(file)
                return SKUProfile.from_dict(data)
        except Exception as exc:
            logger.error(f"Error loading SKU profile '{profile_name}': {exc}")
            return None
