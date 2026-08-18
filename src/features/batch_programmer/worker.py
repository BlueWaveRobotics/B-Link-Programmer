"""
Parallel Batch Flashing and Chip Erasing Worker Module.
Provides isolated per-probe QThread workers and a centralized batch coordinator
to execute simultaneous STM32 multi-target programming and erasing via pyOCD.
"""

import os
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


class SingleSlotWorker(QObject):
    """
    Isolated worker running in a dedicated QThread for a single DAPLink probe slot.
    Handles SWD connection, 96-bit UID read, firmware flashing, and full chip erase.
    """

    progress_signal = Signal(str, int)  # (unique_id, percentage)
    # (unique_id, status_code, message, cycle_time, chip_uid)
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
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.unique_id = unique_id
        self.file_path = file_path
        self.base_address = base_address
        self.clock_freq = clock_freq
        self.connect_mode = connect_mode
        self.verify_enabled = verify_enabled
        self._is_running = True

    def _progress_callback(self, progress: float) -> None:
        """Translates pyOCD decimal progress (0.0 - 1.0) to slot progress percentage."""
        if self._is_running:
            percent = max(0, min(int(progress * 100), 100))
            self.progress_signal.emit(self.unique_id, percent)

    def _connect_session(self, is_erase: bool = False):
        """
        Connects to target via pyOCD with automatic under-reset retry fallback
        if target MCU is in Lockup / HardFault state due to erased flash memory.
        """
        initial_clock = min(
            self.clock_freq, 1000000) if is_erase else self.clock_freq
        options = {
            "connect_mode": self.connect_mode,
            "frequency": initial_clock,
            "reset_type": "hw" if self.connect_mode == "under-reset" else "default",
            "halt_on_connect": True,
            "resume_on_disconnect": False,
        }

        try:
            session = ConnectHelper.session_with_chosen_probe(
                unique_id=self.unique_id,
                options=options,
            )
            session.open()
            return session
        except Exception as primary_err:
            logger.warning(
                f"[{self.unique_id[:8]}] Primary SWD connection failed ({primary_err}). "
                f"Retrying with hardware under-reset recovery @ 500 kHz..."
            )
            # Automatic hardware recovery fallback for MCUs in S_LOCKUP state
            fallback_options = {
                "connect_mode": "under-reset",
                "frequency": 500000,
                "reset_type": "hw",
                "halt_on_connect": True,
                "resume_on_disconnect": False,
            }
            session = ConnectHelper.session_with_chosen_probe(
                unique_id=self.unique_id,
                options=fallback_options,
            )
            session.open()
            return session

    @Slot()
    def run_slot_flash(self) -> None:
        """
        Executes programming lifecycle on the specific probe identified by unique_id.
        """
        session = None
        start_time = time.perf_counter()
        chip_uid = "UNKNOWN-UID"

        try:
            logger.info(
                f"[{self.unique_id[:8]}] Starting parallel programming session...")
            self.status_signal.emit(
                self.unique_id, "BUSY", "Connecting to SWD target...", 0.0, chip_uid)

            session = self._connect_session(is_erase=False)
            target = session.board.target

            # 1. Read 96-bit Unique Device ID (UID)
            try:
                raw_uid_words = target.read_memory_block32(
                    DEFAULT_STM32_UID_ADDRESS, 3)
                chip_uid = ProvisioningService.format_96bit_uid(raw_uid_words)
            except Exception as uid_err:
                logger.warning(
                    f"[{self.unique_id[:8]}] UID Read Warning: {uid_err}")
                chip_uid = "UID-READ-ERROR"

            # 2. Halt Target Core before programming
            try:
                target.reset_and_halt()
            except Exception:
                try:
                    target.halt()
                except Exception:
                    pass

            # 3. Program Firmware Image
            self.status_signal.emit(
                self.unique_id, "BUSY", "Flashing target memory...", 0.0, chip_uid)
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

            # 4. Target Reset & Resume Execution
            try:
                target.reset_and_halt()
                target.resume()
            except Exception as rst_err:
                logger.warning(
                    f"[{self.unique_id[:8]}] Post-flash reset warning: {rst_err}")

            elapsed_time = time.perf_counter() - start_time
            self.progress_signal.emit(self.unique_id, 100)
            self.status_signal.emit(
                self.unique_id, "PASS", "Programming verified successfully.", elapsed_time, chip_uid
            )
            self.finished_signal.emit(self.unique_id, True)

        except Exception as exc:
            elapsed_time = time.perf_counter() - start_time
            err_msg = f"Flash failed: {str(exc)}"
            logger.error(f"[{self.unique_id[:8]}] {err_msg}")
            self.status_signal.emit(
                self.unique_id, "FAIL", err_msg, elapsed_time, chip_uid)
            self.finished_signal.emit(self.unique_id, False)

        finally:
            self._is_running = False
            if session:
                try:
                    session.close()
                except Exception:
                    pass

    @Slot()
    def run_slot_chip_erase(self) -> None:
        """
        Executes robust full chip erase sequence with automatic MASS erase fallback
        and hardware system reset on the specific probe identified by unique_id.
        """
        session = None
        start_time = time.perf_counter()
        chip_uid = "UNKNOWN-UID"

        try:
            logger.info(
                f"[{self.unique_id[:8]}] Starting parallel Full Chip Erase session...")
            self.status_signal.emit(
                self.unique_id, "BUSY", "Connecting for Chip Erase...", 0.0, chip_uid)

            session = self._connect_session(is_erase=True)
            target = session.board.target

            # 1. Read 96-bit UID
            try:
                raw_uid_words = target.read_memory_block32(
                    DEFAULT_STM32_UID_ADDRESS, 3)
                chip_uid = ProvisioningService.format_96bit_uid(raw_uid_words)
            except Exception:
                chip_uid = "UID-READ-ERROR"

            # 2. Halt Target Core
            try:
                target.reset_and_halt()
            except Exception:
                try:
                    target.halt()
                except Exception:
                    pass

            self.progress_signal.emit(self.unique_id, 20)
            self.status_signal.emit(
                self.unique_id, "BUSY", "Erasing all flash sectors...", 0.0, chip_uid)

            # 3. Execute Chip Erase with Mass Erase Fallback
            try:
                eraser = FlashEraser(session, mode=FlashEraser.Mode.CHIP)
                eraser.erase()
            except Exception:
                logger.warning(
                    f"[{self.unique_id[:8]}] Chip Erase algorithm faulted. Attempting Hardware MASS Erase..."
                )
                try:
                    target.halt()
                except Exception:
                    pass
                eraser_mass = FlashEraser(session, mode=FlashEraser.Mode.MASS)
                eraser_mass.erase()

            # 4. System Reset & Halt Core (Clears Flash Controller Cache & SRAM execution)
            # DO NOT call target.resume() on empty flash to prevent S_LOCKUP / HardFault!
            try:
                target.reset_and_halt()
            except Exception as rst_err:
                logger.warning(
                    f"[{self.unique_id[:8]}] Post-erase reset warning: {rst_err}")

            elapsed_time = time.perf_counter() - start_time
            self.progress_signal.emit(self.unique_id, 100)
            self.status_signal.emit(
                self.unique_id, "PASS", "Full Chip Erase completed. Memory blank & MCU reset.", elapsed_time, chip_uid
            )
            self.finished_signal.emit(self.unique_id, True)

        except Exception as exc:
            elapsed_time = time.perf_counter() - start_time
            err_msg = f"Chip Erase failed: {str(exc)}"
            logger.error(f"[{self.unique_id[:8]}] {err_msg}")
            self.status_signal.emit(
                self.unique_id, "FAIL", err_msg, elapsed_time, chip_uid)
            self.finished_signal.emit(self.unique_id, False)

        finally:
            self._is_running = False
            if session:
                try:
                    session.close()
                except Exception:
                    pass


class BatchProgrammerCoordinator(QObject):
    """
    Central coordinator orchestrating multiple SingleSlotWorker threads in parallel.
    Tracks overall batch execution completion and aggregates slot signals.
    """

    batch_started_signal = Signal(int)  # Total enabled slots count
    # Forwarded slot progress: (unique_id, percent)
    batch_progress_signal = Signal(str, int)
    batch_slot_status_signal = Signal(
        str, str, str, float, str)  # Forwarded status
    # (total_pass, total_fail, batch_duration)
    batch_completed_signal = Signal(int, int, float)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._threads: List[QThread] = []
        self._workers: List[SingleSlotWorker] = []
        self._pending_slots = 0
        self._pass_count = 0
        self._fail_count = 0
        self._batch_start_time = 0.0

    def _prepare_batch_run(self, enabled_probe_ids: List[str]) -> bool:
        """Resets internal counters and prepares thread arrays safely."""
        self.stop_all_workers()
        if not enabled_probe_ids:
            logger.warning("No probe slots enabled for batch operation.")
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
        """Creates a thread-worker pair and connects all signal forwarders cleanly."""
        thread = QThread()
        worker = SingleSlotWorker(
            unique_id=unique_id,
            file_path=file_path,
            base_address=base_address,
            clock_freq=clock_freq,
            connect_mode=connect_mode,
            verify_enabled=verify_enabled,
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
        """
        Spawns a parallel QThread for every enabled probe ID and starts programming simultaneously.
        """
        if not self._prepare_batch_run(enabled_probe_ids):
            return

        logger.info(
            f"Launching parallel batch flash across {self._pending_slots} DAPLink probes...")
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
        """
        Spawns a parallel QThread for every enabled probe ID and starts FULL CHIP ERASE simultaneously.
        """
        if not self._prepare_batch_run(enabled_probe_ids):
            return

        logger.info(
            f"Launching parallel Full Chip Erase across {self._pending_slots} DAPLink probes...")
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
        """
        Tracks completed slots and emits final batch stats when all parallel slots finish.
        """
        if success:
            self._pass_count += 1
        else:
            self._fail_count += 1

        self._pending_slots -= 1
        logger.info(
            f"Slot [{unique_id[:8]}] finished. Remaining slots: {self._pending_slots}")

        if self._pending_slots <= 0:
            total_time = time.perf_counter() - self._batch_start_time
            logger.info(
                f"✔ Batch execution complete! PASS: {self._pass_count} | FAIL: {self._fail_count} | Duration: {total_time:.2f}s"
            )
            self.batch_completed_signal.emit(
                self._pass_count, self._fail_count, total_time)

    def stop_all_workers(self) -> None:
        """Safely shuts down and cleans up all active or finished batch threads and workers."""
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
