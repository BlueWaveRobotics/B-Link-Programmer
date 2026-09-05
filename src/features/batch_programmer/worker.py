# """
# Parallel Batch Flashing and Chip Erasing Worker Module.
# Provides isolated per-probe QThread workers and a centralized batch coordinator
# to execute simultaneous multi-vendor ARM multi-target programming and erasing via pyOCD.
# """

# import os
# import time
# from typing import List, Optional
# from PySide6.QtCore import QObject, QThread, Signal, Slot
# from pyocd.core.helpers import ConnectHelper
# from pyocd.flash.file_programmer import FileProgrammer
# from pyocd.flash.eraser import FlashEraser

# from src.common import get_logger
# from src.features.production_programmer.provisioning import ProvisioningService

# logger = get_logger("BatchProgrammerWorker")

# DEFAULT_STM32_UID_ADDRESS = 0x1FFFF7E8


# class SingleSlotWorker(QObject):
#     """
#     Isolated worker running in a dedicated QThread for a single DAPLink probe slot.
#     Handles SWD connection, UID read, firmware flashing, and full chip erase.
#     """

#     progress_signal = Signal(str, int)  # (unique_id, percentage)
#     # (unique_id, status_code, message, cycle_time, chip_uid)
#     status_signal = Signal(str, str, str, float, str)
#     finished_signal = Signal(str, bool)  # (unique_id, success)

#     def __init__(
#         self,
#         unique_id: str,
#         file_path: str = "",
#         base_address: int = 0x08000000,
#         clock_freq: int = 1000000,
#         connect_mode: str = "under-reset",
#         verify_enabled: bool = True,
#         target_type: str = "auto",  # 🌟 پذیرش نوع میکروی انتخابی
#         parent: Optional[QObject] = None,
#     ):
#         super().__init__(parent)
#         self.unique_id = unique_id
#         self.file_path = file_path
#         self.base_address = base_address
#         self.clock_freq = clock_freq
#         self.connect_mode = connect_mode
#         self.verify_enabled = verify_enabled
#         self.target_type = target_type  # 🌟 ذخیره نوع میکرو
#         self._is_running = True

#     def _progress_callback(self, progress: float) -> None:
#         """Translates pyOCD decimal progress (0.0 - 1.0) to slot progress percentage."""
#         if self._is_running:
#             percent = max(0, min(int(progress * 100), 100))
#             self.progress_signal.emit(self.unique_id, percent)

#     def _connect_session(self, is_erase: bool = False):
#         """
#         Connects to target via pyOCD using the specified target_type.
#         """
#         initial_clock = min(
#             self.clock_freq, 1000000) if is_erase else self.clock_freq

#         # تعیین تارگت انتخابی برای pyOCD
#         resolved_target = "cortex_m" if self.target_type in [
#             "auto", "", "none"] else self.target_type

#         options = {
#             "connect_mode": self.connect_mode,
#             "frequency": initial_clock,
#             "reset_type": "hw" if self.connect_mode == "under-reset" else "default",
#             "halt_on_connect": True,
#             "resume_on_disconnect": False,
#             "target_override": resolved_target,  # 🌟 اعمال تارگت روی اتصال pyOCD
#         }

#         try:
#             session = ConnectHelper.session_with_chosen_probe(
#                 unique_id=self.unique_id,
#                 options=options,
#             )
#             session.open()
#             return session
#         except Exception as primary_err:
#             logger.warning(
#                 f"[{self.unique_id[:8]}] Primary SWD connection failed ({primary_err}). "
#                 f"Retrying with hardware under-reset recovery @ 500 kHz..."
#             )
#             fallback_options = {
#                 "connect_mode": "under-reset",
#                 "frequency": 500000,
#                 "reset_type": "hw",
#                 "halt_on_connect": True,
#                 "resume_on_disconnect": False,
#                 "target_override": resolved_target,  # 🌟 اعمال تارگت در حالت Fallback
#             }
#             session = ConnectHelper.session_with_chosen_probe(
#                 unique_id=self.unique_id,
#                 options=fallback_options,
#             )
#             session.open()
#             return session

#     @Slot()
#     def run_slot_flash(self) -> None:
#         """Executes programming lifecycle on the specific probe identified by unique_id."""
#         session = None
#         start_time = time.perf_counter()
#         chip_uid = "UNKNOWN-UID"

#         try:
#             logger.info(
#                 f"[{self.unique_id[:8]}] Starting parallel programming session for '{self.target_type}'...")
#             self.status_signal.emit(
#                 self.unique_id, "BUSY", "Connecting to SWD target...", 0.0, chip_uid
#             )

#             session = self._connect_session(is_erase=False)
#             target = session.board.target

#             # 1. Read UID (فقط برای بردهای ST یا در صورت خواندن موفقیت‌آمیز)
#             if "stm32" in str(self.target_type).lower() or self.target_type == "auto":
#                 try:
#                     raw_uid_words = target.read_memory_block32(
#                         DEFAULT_STM32_UID_ADDRESS, 3)
#                     chip_uid = ProvisioningService.format_96bit_uid(
#                         raw_uid_words)
#                 except Exception:
#                     chip_uid = "UNIVERSAL-UID"
#             else:
#                 chip_uid = f"{self.target_type.upper()}-TARGET"

#             # 2. Halt Target Core before programming
#             try:
#                 target.reset_and_halt()
#             except Exception:
#                 try:
#                     target.halt()
#                 except Exception:
#                     pass

#             # 3. Program Firmware Image
#             self.status_signal.emit(
#                 self.unique_id, "BUSY", "Flashing target memory...", 0.0, chip_uid
#             )
#             programmer = FileProgrammer(
#                 session,
#                 progress=self._progress_callback,
#                 chip_erase="sector",
#             )
#             programmer.program(
#                 self.file_path,
#                 base_address=self.base_address,
#                 verify=self.verify_enabled,
#             )

#             # 4. Target Reset & Resume Execution
#             try:
#                 target.reset_and_halt()
#                 target.resume()
#             except Exception as rst_err:
#                 logger.warning(
#                     f"[{self.unique_id[:8]}] Post-flash reset warning: {rst_err}")

#             elapsed_time = time.perf_counter() - start_time
#             self.progress_signal.emit(self.unique_id, 100)
#             self.status_signal.emit(
#                 self.unique_id, "PASS", "Programming verified successfully.", elapsed_time, chip_uid
#             )
#             self.finished_signal.emit(self.unique_id, True)

#         except Exception as exc:
#             elapsed_time = time.perf_counter() - start_time
#             err_msg = f"Flash failed: {str(exc)}"
#             logger.error(f"[{self.unique_id[:8]}] {err_msg}")
#             self.status_signal.emit(
#                 self.unique_id, "FAIL", err_msg, elapsed_time, chip_uid
#             )
#             self.finished_signal.emit(self.unique_id, False)

#         finally:
#             self._is_running = False
#             if session:
#                 try:
#                     session.close()
#                 except Exception:
#                     pass

#     @Slot()
#     def run_slot_chip_erase(self) -> None:
#         """Executes full chip erase sequence on the specific probe slot."""
#         session = None
#         start_time = time.perf_counter()
#         chip_uid = "UNKNOWN-UID"

#         try:
#             logger.info(
#                 f"[{self.unique_id[:8]}] Starting parallel Full Chip Erase session...")
#             self.status_signal.emit(
#                 self.unique_id, "BUSY", "Connecting for Chip Erase...", 0.0, chip_uid
#             )

#             session = self._connect_session(is_erase=True)
#             target = session.board.target

#             # Halt Target Core
#             try:
#                 target.reset_and_halt()
#             except Exception:
#                 try:
#                     target.halt()
#                 except Exception:
#                     pass

#             self.progress_signal.emit(self.unique_id, 20)
#             self.status_signal.emit(
#                 self.unique_id, "BUSY", "Erasing all flash sectors...", 0.0, chip_uid
#             )

#             # Execute Chip Erase
#             try:
#                 eraser = FlashEraser(session, mode=FlashEraser.Mode.CHIP)
#                 eraser.erase()
#             except Exception:
#                 logger.warning(
#                     f"[{self.unique_id[:8]}] Chip Erase algorithm faulted. Attempting Hardware MASS Erase..."
#                 )
#                 try:
#                     target.halt()
#                 except Exception:
#                     pass
#                 eraser_mass = FlashEraser(session, mode=FlashEraser.Mode.MASS)
#                 eraser_mass.erase()

#             try:
#                 target.reset_and_halt()
#             except Exception as rst_err:
#                 logger.warning(
#                     f"[{self.unique_id[:8]}] Post-erase reset warning: {rst_err}")

#             elapsed_time = time.perf_counter() - start_time
#             self.progress_signal.emit(self.unique_id, 100)
#             self.status_signal.emit(
#                 self.unique_id, "PASS", "Full Chip Erase completed. Memory blank & MCU reset.", elapsed_time, chip_uid
#             )
#             self.finished_signal.emit(self.unique_id, True)

#         except Exception as exc:
#             elapsed_time = time.perf_counter() - start_time
#             err_msg = f"Chip Erase failed: {str(exc)}"
#             logger.error(f"[{self.unique_id[:8]}] {err_msg}")
#             self.status_signal.emit(
#                 self.unique_id, "FAIL", err_msg, elapsed_time, chip_uid
#             )
#             self.finished_signal.emit(self.unique_id, False)

#         finally:
#             self._is_running = False
#             if session:
#                 try:
#                     session.close()
#                 except Exception:
#                     pass


# class BatchProgrammerCoordinator(QObject):
#     """
#     Central coordinator orchestrating multiple SingleSlotWorker threads in parallel.
#     """

#     batch_started_signal = Signal(int)
#     batch_progress_signal = Signal(str, int)
#     batch_slot_status_signal = Signal(str, str, str, float, str)
#     batch_completed_signal = Signal(int, int, float)

#     def __init__(self, parent: Optional[QObject] = None):
#         super().__init__(parent)
#         self._threads: List[QThread] = []
#         self._workers: List[SingleSlotWorker] = []
#         self._pending_slots = 0
#         self._pass_count = 0
#         self._fail_count = 0
#         self._batch_start_time = 0.0
#         self.target_type = "auto"  # 🌟 ذخیره نوع میکرو در سطح هماهنگ‌کننده

#     def _prepare_batch_run(self, enabled_probe_ids: List[str]) -> bool:
#         self.stop_all_workers()
#         if not enabled_probe_ids:
#             logger.warning("No probe slots enabled for batch operation.")
#             self.batch_completed_signal.emit(0, 0, 0.0)
#             return False

#         self._pending_slots = len(enabled_probe_ids)
#         self._pass_count = 0
#         self._fail_count = 0
#         self._batch_start_time = time.perf_counter()
#         self.batch_started_signal.emit(self._pending_slots)
#         return True

#     def _create_and_wire_worker(
#         self,
#         unique_id: str,
#         file_path: str = "",
#         base_address: int = 0x08000000,
#         clock_freq: int = 1000000,
#         connect_mode: str = "under-reset",
#         verify_enabled: bool = True,
#     ) -> tuple[QThread, SingleSlotWorker]:
#         thread = QThread()
#         worker = SingleSlotWorker(
#             unique_id=unique_id,
#             file_path=file_path,
#             base_address=base_address,
#             clock_freq=clock_freq,
#             connect_mode=connect_mode,
#             verify_enabled=verify_enabled,
#             target_type=self.target_type,  # 🌟 پاس دادن تارگت انتخابی به ورکر اسلات
#         )
#         worker.moveToThread(thread)

#         worker.progress_signal.connect(self.batch_progress_signal.emit)
#         worker.status_signal.connect(self.batch_slot_status_signal.emit)
#         worker.finished_signal.connect(self._on_slot_finished)
#         worker.finished_signal.connect(lambda _, __, t=thread: t.quit())

#         self._threads.append(thread)
#         self._workers.append(worker)
#         return thread, worker

#     @Slot(list, str, int, int, str, bool)
#     def start_batch_flashing(
#         self,
#         enabled_probe_ids: List[str],
#         file_path: str,
#         base_address: int = 0x08000000,
#         clock_freq: int = 1000000,
#         connect_mode: str = "under-reset",
#         verify_enabled: bool = True,
#     ) -> None:
#         if not self._prepare_batch_run(enabled_probe_ids):
#             return

#         logger.info(
#             f"Launching parallel batch flash across {self._pending_slots} B-Link probes (Target: '{self.target_type}')..."
#         )
#         for unique_id in enabled_probe_ids:
#             thread, worker = self._create_and_wire_worker(
#                 unique_id=unique_id,
#                 file_path=file_path,
#                 base_address=base_address,
#                 clock_freq=clock_freq,
#                 connect_mode=connect_mode,
#                 verify_enabled=verify_enabled,
#             )
#             thread.started.connect(worker.run_slot_flash)
#             thread.start()

#     @Slot(list, int, str)
#     def start_batch_chip_erase(
#         self,
#         enabled_probe_ids: List[str],
#         clock_freq: int = 1000000,
#         connect_mode: str = "under-reset",
#     ) -> None:
#         if not self._prepare_batch_run(enabled_probe_ids):
#             return

#         logger.info(
#             f"Launching parallel Full Chip Erase across {self._pending_slots} B-Link probes (Target: '{self.target_type}')..."
#         )
#         for unique_id in enabled_probe_ids:
#             thread, worker = self._create_and_wire_worker(
#                 unique_id=unique_id,
#                 clock_freq=clock_freq,
#                 connect_mode=connect_mode,
#             )
#             thread.started.connect(worker.run_slot_chip_erase)
#             thread.start()

#     @Slot(str, bool)
#     def _on_slot_finished(self, unique_id: str, success: bool) -> None:
#         if success:
#             self._pass_count += 1
#         else:
#             self._fail_count += 1

#         self._pending_slots -= 1
#         if self._pending_slots <= 0:
#             total_time = time.perf_counter() - self._batch_start_time
#             self.batch_completed_signal.emit(
#                 self._pass_count, self._fail_count, total_time
#             )

#     def stop_all_workers(self) -> None:
#         for thread in self._threads:
#             try:
#                 if thread and thread.isRunning():
#                     thread.quit()
#                     thread.wait()
#                 thread.deleteLater()
#             except RuntimeError:
#                 pass

#         for worker in self._workers:
#             try:
#                 worker.deleteLater()
#             except RuntimeError:
#                 pass

#         self._threads.clear()
#         self._workers.clear()
"""
Parallel Batch Flashing and Chip Erasing Worker Module.
Provides isolated per-probe QThread workers and a centralized batch coordinator
to execute simultaneous multi-vendor ARM multi-target programming and erasing via pyOCD.
"""

import os
import glob
import time
from typing import List, Optional
from PySide6.QtCore import QObject, QThread, Signal, Slot
from pyocd.core.helpers import ConnectHelper
from pyocd.flash.file_programmer import FileProgrammer
from pyocd.flash.eraser import FlashEraser

from src.common import get_logger
from src.features.production_programmer.provisioning import ProvisioningService

logger = get_logger("BatchProgrammerWorker")

DEFAULT_STM32_UID_ADDRESS = 0x1FFFF7E8
PACK_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".blink_packs")


class SingleSlotWorker(QObject):
    """
    Isolated worker running in a dedicated QThread for a single DAPLink probe slot.
    Handles SWD connection, UID read, firmware flashing, and full chip erase.
    """

    progress_signal = Signal(str, int)  # (unique_id, percentage)
    status_signal = Signal(str, str, str, float, str)
    finished_signal = Signal(str, bool)  # (unique_id, success)

    def __init__(
        self,
        unique_id: str,
        file_path: str = "",
        base_address: int = 0x08000000,
        clock_freq: int = 1000000,
        connect_mode: str = "under-reset",
        verify_enabled: bool = True,
        target_type: str = "auto",
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.unique_id = unique_id
        self.file_path = file_path
        self.base_address = base_address
        self.clock_freq = clock_freq
        self.connect_mode = connect_mode
        self.verify_enabled = verify_enabled
        self.target_type = target_type
        self._is_running = True

    def _progress_callback(self, progress: float) -> None:
        """Translates pyOCD decimal progress (0.0 - 1.0) to slot progress percentage."""
        if self._is_running:
            percent = max(0, min(int(progress * 100), 100))
            self.progress_signal.emit(self.unique_id, percent)

    def _get_pack_list(self) -> List[str]:
        """Loads cached CMSIS packs for reliable target flash programming."""
        if os.path.exists(PACK_CACHE_DIR):
            packs = glob.glob(os.path.join(PACK_CACHE_DIR, "*.pack"))
            return packs
        return []

    def _connect_session(self, is_erase: bool = False):
        """
        Connects to target via pyOCD using explicit device override or None for auto-discovery.
        """
        initial_clock = min(
            self.clock_freq, 1000000) if is_erase else self.clock_freq

        # If target_type is auto, passing None allows pyOCD to auto-detect the ST/ARM part
        target_override = None if self.target_type in [
            "auto", "", "none", None] else self.target_type
        packs = self._get_pack_list()

        print(
            f"[DEBUG-BATCH-WORKER {self.unique_id[:8]}] Connecting -> Target Override: {target_override}, Clock: {initial_clock}Hz, Mode: {self.connect_mode}")
        if packs:
            print(
                f"[DEBUG-BATCH-WORKER {self.unique_id[:8]}] Loaded Packs: {packs}")

        options = {
            "connect_mode": self.connect_mode,
            "frequency": initial_clock,
            "reset_type": "hw" if self.connect_mode == "under-reset" else "default",
            "halt_on_connect": True,
            "resume_on_disconnect": False,
            "target_override": target_override,
            "pack": packs if packs else None
        }

        try:
            session = ConnectHelper.session_with_chosen_probe(
                unique_id=self.unique_id,
                options=options,
            )
            session.open()
            print(
                f"[DEBUG-BATCH-WORKER {self.unique_id[:8]}] Session established successfully with part: {getattr(session.board.target, 'part_number', 'Generic')}")
            return session
        except Exception as primary_err:
            print(
                f"[DEBUG-BATCH-WORKER {self.unique_id[:8]}] Primary connection failed: {primary_err}. Attempting recovery fallback...")
            fallback_options = {
                "connect_mode": "under-reset",
                "frequency": 500000,
                "reset_type": "hw",
                "halt_on_connect": True,
                "resume_on_disconnect": False,
                "target_override": target_override,
                "pack": packs if packs else None
            }
            session = ConnectHelper.session_with_chosen_probe(
                unique_id=self.unique_id,
                options=fallback_options,
            )
            session.open()
            print(
                f"[DEBUG-BATCH-WORKER {self.unique_id[:8]}] Fallback connection established successfully.")
            return session

    @Slot()
    def run_slot_flash(self) -> None:
        """Executes programming lifecycle on the specific probe identified by unique_id."""
        session = None
        start_time = time.perf_counter()
        chip_uid = "UNKNOWN-UID"

        try:
            print(
                f"[DEBUG-BATCH-WORKER {self.unique_id[:8]}] Starting Flash Programming sequence...")
            self.status_signal.emit(
                self.unique_id, "BUSY", "Connecting to SWD target...", 0.0, chip_uid
            )

            session = self._connect_session(is_erase=False)
            target = session.board.target

            # 1. Read UID
            try:
                raw_uid_words = target.read_memory_block32(
                    DEFAULT_STM32_UID_ADDRESS, 3)
                chip_uid = ProvisioningService.format_96bit_uid(raw_uid_words)
                print(
                    f"[DEBUG-BATCH-WORKER {self.unique_id[:8]}] Target UID: {chip_uid}")
            except Exception as uid_err:
                print(
                    f"[DEBUG-BATCH-WORKER {self.unique_id[:8]}] UID read bypassed: {uid_err}")
                chip_uid = "UNIVERSAL-TARGET"

            # 2. Halt Target Core
            try:
                target.reset_and_halt()
            except Exception:
                try:
                    target.halt()
                except Exception:
                    pass

            # 3. Program Firmware Image
            self.status_signal.emit(
                self.unique_id, "BUSY", "Flashing target memory...", 0.0, chip_uid
            )
            print(
                f"[DEBUG-BATCH-WORKER {self.unique_id[:8]}] Invoking FileProgrammer on file: {self.file_path}")
            programmer = FileProgrammer(
                session,
                progress=self._progress_callback,
                chip_erase="sector",
            )
            programmer.program(
                self.file_path,
                base_address=self.base_address,
                verify=self.verify_enabled,
            )
            print(
                f"[DEBUG-BATCH-WORKER {self.unique_id[:8]}] Programming verified successfully.")

            # 4. Target Reset & Resume Execution
            try:
                target.reset_and_halt()
                target.resume()
            except Exception as rst_err:
                print(
                    f"[DEBUG-BATCH-WORKER {self.unique_id[:8]}] Post-flash reset notice: {rst_err}")

            elapsed_time = time.perf_counter() - start_time
            self.progress_signal.emit(self.unique_id, 100)
            self.status_signal.emit(
                self.unique_id, "PASS", "Programming verified successfully.", elapsed_time, chip_uid
            )
            self.finished_signal.emit(self.unique_id, True)

        except Exception as exc:
            elapsed_time = time.perf_counter() - start_time
            err_msg = f"Flash failed: {str(exc)}"
            print(
                f"[DEBUG-BATCH-WORKER {self.unique_id[:8]} EXCEPTION] {err_msg}")
            self.status_signal.emit(
                self.unique_id, "FAIL", err_msg, elapsed_time, chip_uid
            )
            self.finished_signal.emit(self.unique_id, False)

        finally:
            self._is_running = False
            if session:
                try:
                    session.close()
                    print(
                        f"[DEBUG-BATCH-WORKER {self.unique_id[:8]}] Session closed.")
                except Exception:
                    pass

    @Slot()
    def run_slot_chip_erase(self) -> None:
        """Executes full chip erase sequence on the specific probe slot."""
        session = None
        start_time = time.perf_counter()
        chip_uid = "UNKNOWN-UID"

        try:
            print(
                f"[DEBUG-BATCH-WORKER {self.unique_id[:8]}] Full Chip Erase routine triggered.")
            self.status_signal.emit(
                self.unique_id, "BUSY", "Connecting for Chip Erase...", 0.0, chip_uid
            )

            session = self._connect_session(is_erase=True)
            target = session.board.target

            # Halt Target Core
            print(
                f"[DEBUG-BATCH-WORKER {self.unique_id[:8]}] Halting target core...")
            try:
                target.reset_and_halt()
            except Exception:
                try:
                    target.halt()
                except Exception:
                    pass

            self.progress_signal.emit(self.unique_id, 20)
            self.status_signal.emit(
                self.unique_id, "BUSY", "Erasing all flash sectors...", 0.0, chip_uid
            )

            # Execute Chip Erase
            print(
                f"[DEBUG-BATCH-WORKER {self.unique_id[:8]}] Invoking FlashEraser (CHIP Mode)...")
            try:
                eraser = FlashEraser(session, mode=FlashEraser.Mode.CHIP)
                eraser.erase()
                print(
                    f"[DEBUG-BATCH-WORKER {self.unique_id[:8]}] FlashEraser (CHIP Mode) executed successfully.")
            except Exception as e_chip:
                print(
                    f"[DEBUG-BATCH-WORKER {self.unique_id[:8]} WARNING] Mode.CHIP failed ({e_chip}). Attempting Mode.MASS fallback...")
                try:
                    target.halt()
                except Exception:
                    pass
                eraser_mass = FlashEraser(session, mode=FlashEraser.Mode.MASS)
                eraser_mass.erase()
                print(
                    f"[DEBUG-BATCH-WORKER {self.unique_id[:8]}] FlashEraser (MASS Mode) executed successfully.")

            try:
                target.reset_and_halt()
            except Exception as rst_err:
                print(
                    f"[DEBUG-BATCH-WORKER {self.unique_id[:8]}] Post-erase reset warning: {rst_err}")

            elapsed_time = time.perf_counter() - start_time
            self.progress_signal.emit(self.unique_id, 100)
            self.status_signal.emit(
                self.unique_id, "PASS", "Full Chip Erase completed. Memory blank & MCU reset.", elapsed_time, chip_uid
            )
            self.finished_signal.emit(self.unique_id, True)

        except Exception as exc:
            elapsed_time = time.perf_counter() - start_time
            err_msg = f"Chip Erase failed: {str(exc)}"
            print(
                f"[DEBUG-BATCH-WORKER {self.unique_id[:8]} EXCEPTION] {err_msg}")
            self.status_signal.emit(
                self.unique_id, "FAIL", err_msg, elapsed_time, chip_uid
            )
            self.finished_signal.emit(self.unique_id, False)

        finally:
            self._is_running = False
            if session:
                try:
                    session.close()
                    print(
                        f"[DEBUG-BATCH-WORKER {self.unique_id[:8]}] Session closed.")
                except Exception:
                    pass


class BatchProgrammerCoordinator(QObject):
    """
    Central coordinator orchestrating multiple SingleSlotWorker threads in parallel.
    """

    batch_started_signal = Signal(int)
    batch_progress_signal = Signal(str, int)
    batch_slot_status_signal = Signal(str, str, str, float, str)
    batch_completed_signal = Signal(int, int, float)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._threads: List[QThread] = []
        self._workers: List[SingleSlotWorker] = []
        self._pending_slots = 0
        self._pass_count = 0
        self._fail_count = 0
        self._batch_start_time = 0.0
        self.target_type = "auto"

    def _prepare_batch_run(self, enabled_probe_ids: List[str]) -> bool:
        self.stop_all_workers()
        if not enabled_probe_ids:
            print("[DEBUG-COORDINATOR] No probe slots enabled for batch operation.")
            self.batch_completed_signal.emit(0, 0, 0.0)
            return False

        self._pending_slots = len(enabled_probe_ids)
        self._pass_count = 0
        self._fail_count = 0
        self._batch_start_time = time.perf_counter()
        self.batch_started_signal.emit(self._pending_slots)
        return True

    def _create_and_wire_worker(
        self,
        unique_id: str,
        file_path: str = "",
        base_address: int = 0x08000000,
        clock_freq: int = 1000000,
        connect_mode: str = "under-reset",
        verify_enabled: bool = True,
    ) -> tuple[QThread, SingleSlotWorker]:
        thread = QThread()
        worker = SingleSlotWorker(
            unique_id=unique_id,
            file_path=file_path,
            base_address=base_address,
            clock_freq=clock_freq,
            connect_mode=connect_mode,
            verify_enabled=verify_enabled,
            target_type=self.target_type,
        )
        worker.moveToThread(thread)

        worker.progress_signal.connect(self.batch_progress_signal.emit)
        worker.status_signal.connect(self.batch_slot_status_signal.emit)
        worker.finished_signal.connect(self._on_slot_finished)
        worker.finished_signal.connect(lambda _, __, t=thread: t.quit())

        self._threads.append(thread)
        self._workers.append(worker)
        return thread, worker

    @Slot(list, str, int, int, str, bool)
    def start_batch_flashing(
        self,
        enabled_probe_ids: List[str],
        file_path: str,
        base_address: int = 0x08000000,
        clock_freq: int = 1000000,
        connect_mode: str = "under-reset",
        verify_enabled: bool = True,
    ) -> None:
        if not self._prepare_batch_run(enabled_probe_ids):
            return

        print(
            f"[DEBUG-COORDINATOR] Launching Batch Flashing on {self._pending_slots} targets (Target: '{self.target_type}')...")
        for unique_id in enabled_probe_ids:
            thread, worker = self._create_and_wire_worker(
                unique_id=unique_id,
                file_path=file_path,
                base_address=base_address,
                clock_freq=clock_freq,
                connect_mode=connect_mode,
                verify_enabled=verify_enabled,
            )
            thread.started.connect(worker.run_slot_flash)
            thread.start()

    @Slot(list, int, str)
    def start_batch_chip_erase(
        self,
        enabled_probe_ids: List[str],
        clock_freq: int = 1000000,
        connect_mode: str = "under-reset",
    ) -> None:
        if not self._prepare_batch_run(enabled_probe_ids):
            return

        print(
            f"[DEBUG-COORDINATOR] Launching Batch Chip Erase on {self._pending_slots} targets (Target: '{self.target_type}')...")
        for unique_id in enabled_probe_ids:
            thread, worker = self._create_and_wire_worker(
                unique_id=unique_id,
                clock_freq=clock_freq,
                connect_mode=connect_mode,
            )
            thread.started.connect(worker.run_slot_chip_erase)
            thread.start()

    @Slot(str, bool)
    def _on_slot_finished(self, unique_id: str, success: bool) -> None:
        if success:
            self._pass_count += 1
        else:
            self._fail_count += 1

        self._pending_slots -= 1
        print(
            f"[DEBUG-COORDINATOR] Slot {unique_id[:8]} finished (Success={success}). Remaining: {self._pending_slots}")
        if self._pending_slots <= 0:
            total_time = time.perf_counter() - self._batch_start_time
            print(
                f"[DEBUG-COORDINATOR] Batch run complete. PASS={self._pass_count}, FAIL={self._fail_count}, Time={total_time:.2f}s")
            self.batch_completed_signal.emit(
                self._pass_count, self._fail_count, total_time
            )

    def stop_all_workers(self) -> None:
        for thread in self._threads:
            try:
                if thread and thread.isRunning():
                    thread.quit()
                    thread.wait()
                thread.deleteLater()
            except RuntimeError:
                pass

        for worker in self._workers:
            try:
                worker.deleteLater()
            except RuntimeError:
                pass

        self._threads.clear()
        self._workers.clear()
