# src/common/resources.py
from src.common.paths import get_path, get_storage_path

# ///////
DB_FILE_PATH = get_storage_path("production_logs.db")
# ///////

MAIN_ICON = get_path("assets/app.ico")

# /////////////
DLL_LIBUSB = get_path("libusb-1.0.dll")
EXE_DFU = get_path("dfu-util.exe")
# /////////////

# main Icons
ICON_MEMORY = get_path("assets/icons/floppy-disk-regular-full.svg")
ICON_PROGRAMMER = get_path("assets/icons/microchip-solid-full.svg")
ICON_LOCK = get_path("assets/icons/lock-solid-full.svg")
ICON_SERIAL = get_path("assets/icons/display-solid-full.svg")
ICON_BATCH = get_path("assets/icons/network-wired-solid-full.svg")

# memory viewer Icons
ICON_CHEVRON_DOWN = get_path("assets/icons/chevron-down-solid-full.svg")
QSS_CHEVRON_DOWN = ICON_CHEVRON_DOWN.replace("\\", "/")
ICON_ARROWS_ROTATE = get_path("assets/icons/arrows-rotate-solid-full.svg")
ICON_BOOK_OPEN = get_path("assets/icons/book-open-solid-full.svg")
ICON_HOURGLASS = get_path("assets/icons/hourglass-half-solid-full.svg")


# targe_diagnostic Icons
ICON_MAGNIFYING_GLASS = get_path(
    "assets/icons/magnifying-glass-solid-full.svg")
ICON_CLOUD_ARROW_DOWN = get_path(
    "assets/icons/cloud-arrow-down-solid-full.svg")


# production_programmer
ICON_FOLDER_OPEN = get_path("assets/icons/folder-open-solid-full.svg")

# option byte
ICON_BOLT = get_path("assets/icons/bolt-solid-full.svg")

# serial monitor
ICON_PLUG_EXCLAMATION = get_path(
    "assets/icons/plug-circle-exclamation-solid-full.svg")
ICON_PLUG = get_path("assets/icons/plug-solid-full.svg")
ICON_ERASER = get_path("assets/icons/eraser-solid-full.svg")
ICON_PAPER_PLANE = get_path("assets/icons/paper-plane-solid-full.svg")

# for update version
ICON_CODE_MERGE = get_path("assets/icons/code-merge-solid-full.svg")
ICON_TERMINAL = get_path("assets/icons/terminal-solid-full.svg")

# for programing
ICON_PEN_SQUARE = get_path("assets/icons/pen-to-square-solid-full.svg")
