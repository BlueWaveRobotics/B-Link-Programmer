"""
Command-Line Automation Entry Point for B-Link DAPLink Production Suite.
Supports integration with industrial automated test jigs and headless CI/CD pipelines.
"""

import sys
from src.cli.parser import parse_arguments
from src.cli.runner import HeadlessRunner
from src.common import get_logger

logger = get_logger("CLI_Main")


def main() -> int:
    """
    Main entry point for CLI automation. Returns system exit code:
    0 = PASS / SUCCESS
    1 = FAIL / ERROR
    """
    args = parse_arguments()
    runner = HeadlessRunner()

    # 1. Action: List Connected Probes
    if args.list_probes:
        return runner.list_connected_probes()

    # 2. Resolve Parameters (SKU Profile vs Manual CLI Arguments)
    file_path = args.file
    base_addr_str = str(args.address)
    clock_khz = args.clock
    mode = args.mode
    verify = not args.no_verify

    if args.sku:
        profile = runner.profile_manager.load_profile(args.sku)
        if not profile:
            print(
                f"[CLI ERROR] SKU profile '{args.sku}' not found in profiles/ directory.", file=sys.stderr)
            return 1
        file_path = profile.file_path
        base_addr_str = hex(profile.base_address)
        clock_khz = profile.clock_freq // 1000
        mode = profile.connect_mode
        verify = profile.verify_enabled
        print(f"[CLI INFO] Loaded settings from SKU Profile: {profile.name}")

    clock_hz = clock_khz * 1000
    base_address = int(base_addr_str, 16) if base_addr_str.lower(
    ).startswith("0x") else int(base_addr_str)

    # 3. Action: Full Chip Erase
    if args.erase:
        success = runner.run_chip_erase(
            unique_id=args.probe,
            clock_freq=clock_hz,
            connect_mode=mode,
        )
        if not success:
            return 1
        if not args.flash:
            return 0  # Erase-only operation finished successfully

    # 4. Action: Production Flash
    if args.flash:
        if not file_path:
            print(
                "[CLI ERROR] No firmware file specified! Use --file or --sku.", file=sys.stderr)
            return 1

        success = runner.run_production_flash(
            file_path=file_path,
            base_address=base_address,
            clock_freq=clock_hz,
            connect_mode=mode,
            verify_enabled=verify,
            unique_id=args.probe,
        )
        return 0 if success else 1

    # If no valid action was triggered
    print("[CLI ERROR] No primary action specified. Use --flash, --erase, or --list-probes.", file=sys.stderr)
    print("Run 'python cli_main.py --help' for full usage documentation.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
