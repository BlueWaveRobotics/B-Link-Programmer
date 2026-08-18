"""
Command Line Argument Parser for B-Link DAPLink Headless Mode.
Defines industrial automation flags for automated Test Jigs and CI/CD pipelines.
"""

import argparse
from typing import Optional


def build_cli_parser() -> argparse.ArgumentParser:
    """
    Constructs and returns the argument parser for headless automation.
    """
    parser = argparse.ArgumentParser(
        prog="blink-cli",
        description="B-Link Production & Diagnostic Headless Automation Tool",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    # Action Flags (Mutually Exclusive or Combined Commands)
    action_group = parser.add_argument_group("Primary Actions")
    action_group.add_argument(
        "--list-probes",
        action="store_true",
        help="Scan USB bus and print all connected B-Link probe unique IDs.",
    )
    action_group.add_argument(
        "--flash",
        action="store_true",
        help="Execute production firmware flashing sequence.",
    )
    action_group.add_argument(
        "--erase",
        action="store_true",
        help="Execute full chip erase (with automatic Mass Erase fallback).",
    )

    # Target & Probe Selection
    target_group = parser.add_argument_group("Target & Hardware Settings")
    target_group.add_argument(
        "--probe",
        type=str,
        default=None,
        metavar="UNIQUE_ID",
        help="Specify target probe Unique ID. If omitted, uses auto-select or batch mode.",
    )
    target_group.add_argument(
        "--sku",
        type=str,
        default=None,
        metavar="SKU_NAME",
        help="Load pre-configured SKU profile from JSON (overrides manual file/address arguments).",
    )

    # Manual Programming Parameters
    config_group = parser.add_argument_group("Manual Flashing Configuration")
    config_group.add_argument(
        "--file",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to firmware image (.hex / .bin).",
    )
    config_group.add_argument(
        "--address",
        type=str,
        default="0x08000000",
        metavar="HEX_ADDR",
        help="Start flash memory address (default: 0x08000000).",
    )
    config_group.add_argument(
        "--clock",
        type=int,
        default=1000,
        metavar="KHZ",
        help="SWD clock frequency in kHz (default: 1000).",
    )
    config_group.add_argument(
        "--mode",
        type=str,
        choices=["under-reset", "attach", "normal"],
        default="under-reset",
        help="SWD connect mode (default: under-reset).",
    )
    config_group.add_argument(
        "--no-verify",
        action="store_true",
        help="Disable verification step after programming to reduce cycle time.",
    )

    return parser


def parse_arguments(args: Optional[list] = None) -> argparse.Namespace:
    """Parses command-line arguments and returns the namespace."""
    parser = build_cli_parser()
    return parser.parse_args(args)
