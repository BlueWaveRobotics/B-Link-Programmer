"""
Hardware Probe Manager Service for Batch Flashing.
Scans, enumerates, and monitors all connected DAPLink/CMSIS-DAP debug probes
to support parallel multi-target programming.
"""

from typing import List, Dict, Any
from pyocd.core.helpers import ConnectHelper
from src.common import get_logger

logger = get_logger("ProbeManager")


class ProbeInfo:
    """
    Data model representing a detected hardware debug probe.
    """

    def __init__(self, unique_id: str, vendor_name: str, product_name: str):
        self.unique_id = unique_id
        self.vendor_name = vendor_name
        self.product_name = product_name
        self.display_name = f"{product_name} [{unique_id[:8]}...]"

    def to_dict(self) -> Dict[str, Any]:
        """Serializes probe metadata to a standard dictionary."""
        return {
            "unique_id": self.unique_id,
            "vendor_name": self.vendor_name,
            "product_name": self.product_name,
            "display_name": self.display_name,
        }


class ProbeManagerService:
    """
    Service responsible for enumerating active pyOCD hardware probes on USB bus.
    """

    @staticmethod
    def discover_connected_probes() -> List[ProbeInfo]:
        """
        Scans the host system for connected DAPLink or CMSIS-DAP debug probes.
        Returns a list of ProbeInfo instances.
        """
        detected_probes: List[ProbeInfo] = []
        try:
            raw_probes = ConnectHelper.get_all_connected_probes(blocking=False)
            for probe in raw_probes:
                unique_id = getattr(probe, "unique_id", "UNKNOWN_ID")
                vendor_name = getattr(
                    probe, "vendor_name", "B-Link") or "B-Link"
                product_name = getattr(
                    probe, "product_name", "B-Link Probe") or "B-Link Probe"

                info = ProbeInfo(
                    unique_id=unique_id,
                    vendor_name=vendor_name,
                    product_name=product_name,
                )
                detected_probes.append(info)

            logger.info(
                f"Probe scan completed. Total B-Link probes detected: {len(detected_probes)}"
            )
        except Exception as exc:
            logger.error(
                f"Failed to enumerate hardware debug probes: {str(exc)}")

        return detected_probes
