"""
Launches PowerToys utilities by signaling their named events, shows only the
utilities enabled in %LOCALAPPDATA%\\Microsoft\\PowerToys\\settings.json, and
exposes per-utility "open settings" / "run as administrator" as result actions.

Run-as-admin needs no elevation code in the plugin: it just signals a different
named event and PowerToys elevates itself.
"""

from __future__ import annotations

import asyncio
import ctypes
import json
import os
import subprocess
import time
from dataclasses import dataclass

from wox_plugin import (
    ActionContext,
    Context,
    LogLevel,
    Plugin,
    PluginInitParams,
    PublicAPI,
    Query,
    Result,
    ResultAction,
    WoxImage,
)


class CommonSharedConstants:
    """Inbound named events copied verbatim from microsoft/PowerToys.

    Source: src/common/interop/shared_constants.h (main branch, synced 2026-10-21)
    https://github.com/microsoft/PowerToys/blob/main/src/common/interop/shared_constants.h

    Only events that PowerToys itself waits on are listed, so signaling one is
    equivalent to pressing the utility's shortcut. Outbound or self-sync events
    (for example the LightSwitch -> PowerDisplay theme notifications) are omitted
    on purpose: signaling them has no user-visible effect.
    """

    # PowerToys Run / Command Palette
    POWER_LAUNCHER_SHARED_EVENT = "Local\\PowerToysRunInvokeEvent-30f26ad7-d36d-4c0e-ab02-68bb5ff3c4ab"
    CMDPAL_SHOW_EVENT = "Local\\PowerToysCmdPal-ShowEvent-62336fcd-8611-4023-9b30-091a6af4cc5a"

    # Color Picker
    SHOW_COLOR_PICKER_SHARED_EVENT = "Local\\ShowColorPickerEvent-8c46be2a-3e05-4186-b56b-4ae986ef2525"

    # FancyZones
    FANCY_ZONES_EDITOR_TOGGLE_EVENT = "Local\\FancyZones-ToggleEditorEvent-1e174338-06a3-472b-874d-073b21c62f14"

    # Hosts
    SHOW_HOSTS_EVENT = "Local\\Hosts-ShowHostsEvent-5a0c0aae-5ff5-40f5-95c2-20e37ed671f0"
    SHOW_HOSTS_ADMIN_EVENT = "Local\\Hosts-ShowHostsAdminEvent-60ff44e2-efd3-43bf-928a-f4d269f98bec"

    # Measure Tool
    MEASURE_TOOL_TRIGGER_EVENT = "Local\\MeasureToolEvent-3d46745f-09b3-4671-a577-236be7abd199"

    # Shortcut Guide
    SHORTCUT_GUIDE_TRIGGER_EVENT = "Local\\ShortcutGuide-TriggerEvent-d4275ad3-2531-4d19-9252-c0becbd9b496"
    SHORTCUT_GUIDE_WIN_KEY_HOLD_EVENT = "Local\\ShortcutGuide-WinKeyHoldEvent-b5eb7614-d1c4-49d7-9813-ab277aabdd80"

    # Registry Preview
    REGISTRY_PREVIEW_TRIGGER_EVENT = "Local\\RegistryPreviewEvent-4C559468-F75A-4E7F-BC4F-9C9688316687"

    # Crop And Lock
    CROP_AND_LOCK_THUMBNAIL_EVENT = "Local\\PowerToysCropAndLockThumbnailEvent-1637be50-da72-46b2-9220-b32b206b2434"
    CROP_AND_LOCK_REPARENT_EVENT = "Local\\PowerToysCropAndLockReparentEvent-6060860a-76a1-44e8-8d0e-6355785e9c36"
    CROP_AND_LOCK_SCREENSHOT_EVENT = "Local\\PowerToysCropAndLockScreenshotEvent-ff077ab2-8360-4bd1-864a-637389d35593"

    # Environment Variables
    SHOW_ENVIRONMENT_VARIABLES_EVENT = (
        "Local\\PowerToysEnvironmentVariables-ShowEnvironmentVariablesEvent-1021f616-e951-4d64-b231-a8f972159978"
    )
    SHOW_ENVIRONMENT_VARIABLES_ADMIN_EVENT = (
        "Local\\PowerToysEnvironmentVariables-EnvironmentVariablesAdminEvent-8c95d2ad-047c-49a2-9e8b-b4656326cfb2"
    )

    # AlwaysOnTop
    ALWAYS_ON_TOP_PIN_EVENT = "Local\\AlwaysOnTopPinEvent-892e0aa2-cfa8-4cc4-b196-ddeb32314ce8"
    ALWAYS_ON_TOP_INCREASE_OPACITY_EVENT = "Local\\AlwaysOnTopIncreaseOpacityEvent-a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    ALWAYS_ON_TOP_DECREASE_OPACITY_EVENT = "Local\\AlwaysOnTopDecreaseOpacityEvent-b2c3d4e5-f6a7-8901-bcde-f12345678901"

    # Text Extractor
    SHOW_POWEROCR_SHARED_EVENT = "Local\\PowerOCREvent-dc864e06-e1af-4ecc-9078-f98bee745e3a"

    # Workspaces
    WORKSPACES_LAUNCH_EDITOR_EVENT = "Local\\Workspaces-LaunchEditorEvent-a55ff427-cf62-4994-a2cd-9f72139296bf"

    # Awake
    AWAKE_EXIT_EVENT = "Local\\PowerToysAwakeExitEvent-c0d5e305-35fc-4fb5-83ec-f6070cfaf7fe"

    # Advanced Paste
    ADVANCED_PASTE_SHOW_UI_EVENT = "Local\\PowerToys_AdvancedPaste_ShowUI"

    # Mouse Utils
    FIND_MY_MOUSE_TRIGGER_EVENT = "Local\\FindMyMouseTriggerEvent-5a9dc5f4-1c74-4f2f-a66f-1b9b6a2f9b23"
    MOUSE_HIGHLIGHTER_TRIGGER_EVENT = "Local\\MouseHighlighterTriggerEvent-1e3c9c3d-3fdf-4f9a-9a52-31c9b3c3a8f4"
    MOUSE_CROSSHAIRS_TRIGGER_EVENT = "Local\\MouseCrosshairsTriggerEvent-0d4c7f92-0a5c-4f5c-b64b-8a2a2f7e0b21"
    CURSOR_WRAP_TRIGGER_EVENT = "Local\\CursorWrapTriggerEvent-1f8452b5-4e6e-45b3-8b09-13f14a5900c9"
    MOUSE_JUMP_SHOW_PREVIEW_EVENT = "Local\\MouseJumpEvent-aa0be051-3396-4976-b7ba-1a9cc7d236a5"

    # LightSwitch (only the toggle is inbound; the light/dark theme events are
    # LightSwitch -> PowerDisplay notifications and are intentionally not listed)
    LIGHTSWITCH_TOGGLE_EVENT = "Local\\PowerToys-LightSwitch-ToggleEvent-d8dc2f29-8c94-4ca1-8c5f-3e2b1e3c4f5a"

    # ZoomIt
    ZOOMIT_EXIT_EVENT = "Local\\PowerToysZoomIt-ExitEvent-36641ce6-df02-4eac-abea-a3fbf9138220"
    ZOOMIT_ZOOM_EVENT = "Local\\PowerToysZoomIt-ZoomEvent-1e4190d7-94bc-4ad5-adc0-9a8fd07cb393"
    ZOOMIT_DRAW_EVENT = "Local\\PowerToysZoomIt-DrawEvent-56338997-404d-4549-bd9a-d132b6766975"
    ZOOMIT_BREAK_EVENT = "Local\\PowerToysZoomIt-BreakEvent-17f2e63c-4c56-41dd-90a0-2d12f9f50c6b"
    ZOOMIT_LIVEZOOM_EVENT = "Local\\PowerToysZoomIt-LiveZoomEvent-390bf0c7-616f-47dc-bafe-a2d228add20d"
    ZOOMIT_SNIP_EVENT = "Local\\PowerToysZoomIt-SnipEvent-2fd9c211-436d-4f17-a902-2528aaae3e30"
    ZOOMIT_SNIPOCR_EVENT = "Local\\PowerToysZoomIt-SnipOcrEvent-a7c3b1d2-9e4f-4a6b-8d5c-1f2e3a4b5c6d"
    ZOOMIT_SNIPDICTATE_EVENT = "Local\\PowerToysZoomIt-SnipDictateEvent-4b8e6f10-2c73-4f5a-9b21-7d0a6c5e8f43"
    ZOOMIT_RECORD_EVENT = "Local\\PowerToysZoomIt-RecordEvent-74539344-eaad-4711-8e83-23946e424512"

    # Keyboard Manager
    OPEN_NEW_KEYBOARD_MANAGER_EVENT = "Local\\PowerToysOpenNewKeyboardManagerEvent-9c1d2e3f-4b5a-6c7d-8e9f-0a1b2c3d4e5f"

    # Mouse Without Borders
    MWB_TOGGLE_EASY_MOUSE_EVENT = "Local\\PowerToysMWB-ToggleEasyMouseEvent-a9c8d7b6-e5f4-3c2a-1b0d-9e8f7a6b5c4d"
    MWB_RECONNECT_EVENT = "Local\\PowerToysMWB-ReconnectEvent-b8d7c6a5-f4e3-2b1c-0a9d-8e7f6a5b4c3d"

    # PowerDisplay
    TOGGLE_POWER_DISPLAY_EVENT = "Local\\PowerToysPowerDisplay-ToggleEvent-5f1a9c3e-7d2b-4e8f-9a6c-3b5d7e9f1a2c"
    TERMINATE_POWER_DISPLAY_EVENT = "Local\\PowerToysPowerDisplay-TerminateEvent-7b9c2e1f-8a5d-4c3e-9f6b-2a1d8c5e3b7a"
    REFRESH_POWER_DISPLAY_MONITORS_EVENT = "Local\\PowerToysPowerDisplay-RefreshMonitorsEvent-a3f5c8e7-9d1b-4e2f-8c6a-3b5d7e9f1a2c"
    RESCAN_POWER_DISPLAY_MONITORS_EVENT = "Local\\PowerToysPowerDisplay-RescanMonitorsEvent-7f3e8c5a-1d4b-4a9e-bc6f-5d8a2b9e3c4f"

    # Grab And Move
    GRABANDMOVE_EXIT_EVENT = "Local\\PowerToysGrabAndMove-ExitEvent-b8c4d2e3-5f6a-7b8c-9d0e-1f2a3b4c5d6e"

    # Peek
    SHOW_PEEK_SHARED_EVENT = "Local\\ShowPeekEvent"


@dataclass
class UtilityAction:
    """One PowerToys utility entry."""

    title_key: str
    event: str = ""
    keywords: tuple[str, ...] = ()
    icon: str = ""
    settings_link: str = ""
    settings_enabled_name: str = ""  # falls back to settings_link when empty
    admin_event: str = ""
    delayed: bool = False
    open_settings_only: bool = False  # the trailing "PowerToys Settings" entry


# Mirrors the Actions array in PowerToysLauncher.cs (dev branch).
_ACTIONS: list[UtilityAction] = [
    UtilityAction(
        "screen_ruler",
        CommonSharedConstants.MEASURE_TOOL_TRIGGER_EVENT,
        ("screen", "ruler", "measure", "tool"),
        "ScreenRuler.png",
        "MeasureTool",
        "Measure Tool",
    ),
    UtilityAction(
        "shortcut_guide",
        CommonSharedConstants.SHORTCUT_GUIDE_TRIGGER_EVENT,
        ("shortcut", "guide"),
        "ShortcutGuide.png",
        "ShortcutGuide",
        "Shortcut Guide",
    ),
    UtilityAction(
        "shortcut_guide_win_key_hold",
        CommonSharedConstants.SHORTCUT_GUIDE_WIN_KEY_HOLD_EVENT,
        ("shortcut", "guide", "win", "key", "hold"),
        "ShortcutGuide.png",
        "ShortcutGuide",
        "Shortcut Guide",
    ),
    UtilityAction(
        "color_picker",
        CommonSharedConstants.SHOW_COLOR_PICKER_SHARED_EVENT,
        ("color", "picker"),
        "ColorPicker.png",
        "ColorPicker",
    ),
    UtilityAction(
        "always_on_top_pin",
        CommonSharedConstants.ALWAYS_ON_TOP_PIN_EVENT,
        ("always", "top", "pin"),
        "AlwaysOnTop.png",
        "AlwaysOnTop",
        delayed=True,
    ),
    UtilityAction(
        "always_on_top_increase_opacity",
        CommonSharedConstants.ALWAYS_ON_TOP_INCREASE_OPACITY_EVENT,
        ("always", "top", "increase", "opacity"),
        "AlwaysOnTop.png",
        "AlwaysOnTop",
    ),
    UtilityAction(
        "always_on_top_decrease_opacity",
        CommonSharedConstants.ALWAYS_ON_TOP_DECREASE_OPACITY_EVENT,
        ("always", "top", "decrease", "opacity"),
        "AlwaysOnTop.png",
        "AlwaysOnTop",
    ),
    UtilityAction(
        "text_extractor",
        CommonSharedConstants.SHOW_POWEROCR_SHARED_EVENT,
        ("text", "extract", "ocr"),
        "TextExtractor.png",
        "PowerOcr",
        "TextExtractor",
    ),
    UtilityAction("fancy_zones", CommonSharedConstants.FANCY_ZONES_EDITOR_TOGGLE_EVENT, ("fancy", "zones"), "FancyZones.png", "FancyZones"),
    UtilityAction(
        "hosts_file_editor",
        CommonSharedConstants.SHOW_HOSTS_EVENT,
        ("hosts",),
        "Hosts.png",
        "Hosts",
        admin_event=CommonSharedConstants.SHOW_HOSTS_ADMIN_EVENT,
    ),
    UtilityAction(
        "registry_preview",
        CommonSharedConstants.REGISTRY_PREVIEW_TRIGGER_EVENT,
        ("registry", "preview"),
        "RegistryPreview.png",
        "RegistryPreview",
    ),
    UtilityAction(
        "peek",
        CommonSharedConstants.SHOW_PEEK_SHARED_EVENT,
        ("peek", "preview"),
        "Peek.png",
        "Peek",
        delayed=True,
    ),
    UtilityAction(
        "workspaces",
        CommonSharedConstants.WORKSPACES_LAUNCH_EDITOR_EVENT,
        ("workspaces",),
        "Workspaces.png",
        "Workspaces",
    ),
    UtilityAction(
        "crop_and_lock_reparent",
        CommonSharedConstants.CROP_AND_LOCK_REPARENT_EVENT,
        ("crop", "lock", "reparent"),
        "CropAndLock.png",
        "CropAndLock",
        delayed=True,
    ),
    UtilityAction(
        "crop_and_lock_thumbnail",
        CommonSharedConstants.CROP_AND_LOCK_THUMBNAIL_EVENT,
        ("crop", "lock", "thumbnail"),
        "CropAndLock.png",
        "CropAndLock",
        delayed=True,
    ),
    UtilityAction(
        "crop_and_lock_screenshot",
        CommonSharedConstants.CROP_AND_LOCK_SCREENSHOT_EVENT,
        ("crop", "lock", "screenshot"),
        "CropAndLock.png",
        "CropAndLock",
        delayed=True,
    ),
    UtilityAction(
        "environment_variables",
        CommonSharedConstants.SHOW_ENVIRONMENT_VARIABLES_EVENT,
        ("environment", "variables"),
        "EnvironmentVariables.png",
        "EnvironmentVariables",
        admin_event=CommonSharedConstants.SHOW_ENVIRONMENT_VARIABLES_ADMIN_EVENT,
    ),
    UtilityAction(
        "powertoys_run",
        CommonSharedConstants.POWER_LAUNCHER_SHARED_EVENT,
        ("powertoys", "run"),
        "PowerToysRun.png",
        "Run",
        "PowerToys Run",
    ),
    UtilityAction(
        "command_palette",
        CommonSharedConstants.CMDPAL_SHOW_EVENT,
        ("command", "palette", "cmd"),
        "CmdPal.png",
        "CmdPal",
    ),
    UtilityAction("awake_exit", CommonSharedConstants.AWAKE_EXIT_EVENT, ("exit", "awake"), "Awake.png", "Awake"),
    UtilityAction(
        "advanced_paste_show_ui",
        CommonSharedConstants.ADVANCED_PASTE_SHOW_UI_EVENT,
        ("advanced", "paste"),
        "AdvancedPaste.png",
        "AdvancedPaste",
    ),
    UtilityAction(
        "find_my_mouse",
        CommonSharedConstants.FIND_MY_MOUSE_TRIGGER_EVENT,
        ("find", "mouse"),
        "FindMyMouse.png",
        "MouseUtils",
        "FindMyMouse",
        delayed=True,
    ),
    UtilityAction(
        "mouse_highlighter",
        CommonSharedConstants.MOUSE_HIGHLIGHTER_TRIGGER_EVENT,
        ("mouse", "highlighter"),
        "MouseHighlighter.png",
        "MouseUtils",
        "MouseHighlighter",
    ),
    UtilityAction(
        "mouse_crosshairs",
        CommonSharedConstants.MOUSE_CROSSHAIRS_TRIGGER_EVENT,
        ("mouse", "crosshairs"),
        "MouseCrosshairs.png",
        "MouseUtils",
        "MousePointerCrosshairs",
    ),
    UtilityAction(
        "cursor_wrap",
        CommonSharedConstants.CURSOR_WRAP_TRIGGER_EVENT,
        ("cursor", "wrap"),
        "CursorWrap.png",
        "MouseUtils",
        "CursorWrap",
    ),
    UtilityAction(
        "mouse_jump",
        CommonSharedConstants.MOUSE_JUMP_SHOW_PREVIEW_EVENT,
        ("mouse", "jump"),
        "MouseJump.png",
        "MouseUtils",
        "MouseJump",
    ),
    UtilityAction(
        "light_switch_toggle",
        CommonSharedConstants.LIGHTSWITCH_TOGGLE_EVENT,
        ("light", "switch", "toggle", "theme"),
        "LightSwitch.png",
        "LightSwitch",
    ),
    UtilityAction("zoomit_exit", CommonSharedConstants.ZOOMIT_EXIT_EVENT, ("zoomit", "exit"), "ZoomIt.png", "ZoomIt"),
    UtilityAction("zoomit_zoom", CommonSharedConstants.ZOOMIT_ZOOM_EVENT, ("zoomit", "zoom"), "ZoomIt.png", "ZoomIt"),
    UtilityAction("zoomit_draw", CommonSharedConstants.ZOOMIT_DRAW_EVENT, ("zoomit", "draw"), "ZoomIt.png", "ZoomIt"),
    UtilityAction("zoomit_break", CommonSharedConstants.ZOOMIT_BREAK_EVENT, ("zoomit", "break"), "ZoomIt.png", "ZoomIt"),
    UtilityAction(
        "zoomit_live_zoom",
        CommonSharedConstants.ZOOMIT_LIVEZOOM_EVENT,
        ("zoomit", "live", "zoom"),
        "ZoomIt.png",
        "ZoomIt",
    ),
    UtilityAction("zoomit_snip", CommonSharedConstants.ZOOMIT_SNIP_EVENT, ("zoomit", "snip"), "ZoomIt.png", "ZoomIt"),
    UtilityAction(
        "zoomit_snip_ocr",
        CommonSharedConstants.ZOOMIT_SNIPOCR_EVENT,
        ("zoomit", "snip", "ocr"),
        "ZoomIt.png",
        "ZoomIt",
    ),
    UtilityAction(
        "zoomit_snip_dictate",
        CommonSharedConstants.ZOOMIT_SNIPDICTATE_EVENT,
        ("zoomit", "snip", "dictate"),
        "ZoomIt.png",
        "ZoomIt",
    ),
    UtilityAction("zoomit_record", CommonSharedConstants.ZOOMIT_RECORD_EVENT, ("zoomit", "record"), "ZoomIt.png", "ZoomIt"),
    UtilityAction(
        "open_new_keyboard_manager",
        CommonSharedConstants.OPEN_NEW_KEYBOARD_MANAGER_EVENT,
        ("keyboard", "manager"),
        "KeyboardManager.png",
        "KBM",
        "Keyboard Manager",
    ),
    UtilityAction(
        "toggle_easy_mouse",
        CommonSharedConstants.MWB_TOGGLE_EASY_MOUSE_EVENT,
        ("toggle", "easy", "mouse"),
        "MouseWithoutBorders.png",
        "MouseWithoutBorders",
    ),
    UtilityAction(
        "reconnect_mouse",
        CommonSharedConstants.MWB_RECONNECT_EVENT,
        ("reconnect", "mouse"),
        "MouseWithoutBorders.png",
        "MouseWithoutBorders",
    ),
    UtilityAction(
        "power_display_toggle",
        CommonSharedConstants.TOGGLE_POWER_DISPLAY_EVENT,
        ("display", "toggle"),
        "PowerDisplay.png",
        "PowerDisplay",
    ),
    UtilityAction(
        "power_display_terminate",
        CommonSharedConstants.TERMINATE_POWER_DISPLAY_EVENT,
        ("display", "terminate"),
        "PowerDisplay.png",
        "PowerDisplay",
    ),
    UtilityAction(
        "power_display_refresh_monitors",
        CommonSharedConstants.REFRESH_POWER_DISPLAY_MONITORS_EVENT,
        ("display", "refresh", "monitors"),
        "PowerDisplay.png",
        "PowerDisplay",
    ),
    UtilityAction(
        "power_display_rescan_monitors",
        CommonSharedConstants.RESCAN_POWER_DISPLAY_MONITORS_EVENT,
        ("display", "rescan", "monitors"),
        "PowerDisplay.png",
        "PowerDisplay",
    ),
    UtilityAction(
        "grab_and_move_exit",
        CommonSharedConstants.GRABANDMOVE_EXIT_EVENT,
        ("grab", "move", "exit"),
        "GrabAndMove.png",
        "GrabAndMove",
    ),
    UtilityAction("settings", icon="PowerToys.png", keywords=("settings",), settings_link="PowerToys", open_settings_only=True),
]


_ICON_URL_BASE = "https://cdn.jsdelivr.net/gh/microsoft/PowerToys/src/settings-ui/Settings.UI/Assets/Settings/Icons/"


_EVENT_MODIFY_STATE = 0x0002
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.OpenEventW.argtypes = (ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p)
_kernel32.OpenEventW.restype = ctypes.c_void_p
_kernel32.SetEvent.argtypes = (ctypes.c_void_p,)
_kernel32.SetEvent.restype = ctypes.c_bool
_kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
_kernel32.CloseHandle.restype = ctypes.c_bool


def _signal_event(name: str) -> bool:
    """Signal an existing auto-reset named event owned by PowerToys.

    Mirrors ``EventWaitHandle.OpenExisting(name).Set()``: only events that
    already exist are signaled, so a missing PowerToys event is reported as a
    failure instead of silently creating an orphan event.
    """
    handle = _kernel32.OpenEventW(_EVENT_MODIFY_STATE, False, name)
    if not handle:
        return False
    try:
        return bool(_kernel32.SetEvent(handle))
    finally:
        _kernel32.CloseHandle(handle)


def _find_powertoys_exe() -> str | None:
    candidates = (
        os.path.expandvars(r"%LOCALAPPDATA%\PowerToys\PowerToys.exe"),
        os.path.expandvars(r"%ProgramFiles%\PowerToys\PowerToys.exe"),
        os.path.expandvars(r"%USERPROFILE%\scoop\apps\powertoys\current\PowerToys.exe"),
    )
    return next((p for p in candidates if os.path.isfile(p)), None)


def _is_powertoys_running() -> bool:
    try:
        proc = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq PowerToys.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return "PowerToys.exe" in proc.stdout


def _resolve_icon(icon_name: str, cache: dict[str, WoxImage]) -> WoxImage:
    """Resolve a utility icon: local PowerToys install first, jsdelivr URL as fallback."""
    if icon_name in cache:
        return cache[icon_name]
    rel = os.path.join("PowerToys", "WinUI3Apps", "Assets", "Settings", "Icons", icon_name)
    image: WoxImage | None = None
    for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles", "")):
        if base:
            path = os.path.join(base, rel)
            if os.path.isfile(path):
                image = WoxImage.new_absolute(path)
                break
    if image is None:
        path = os.path.expandvars(r"%USERPROFILE%\scoop\apps\powertoys\current\WinUI3Apps\Assets\Settings\Icons\\" + icon_name)
        if os.path.isfile(path):
            image = WoxImage.new_absolute(path)
        else:
            image = WoxImage.new_url(_ICON_URL_BASE + icon_name)
    cache[icon_name] = image
    return image


class PowerToysSettings:
    """Reads %LOCALAPPDATA%\\Microsoft\\PowerToys\\settings.json (the 'enabled' map)."""

    def __init__(self) -> None:
        self._path = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\PowerToys\settings.json")
        self._mtime: float = 0.0
        self._enabled: dict[str, bool] = {}

    def refresh(self) -> None:
        try:
            mtime = os.path.getmtime(self._path)
        except OSError:
            return
        if mtime == self._mtime:
            return
        for _ in range(2):  # initial try + one retry
            try:
                with open(self._path, encoding="utf-8") as f:
                    data = json.load(f)
                enabled = data.get("enabled", {})
                self._enabled = {k: bool(v) for k, v in enabled.items()} if isinstance(enabled, dict) else {}
                self._mtime = mtime
                return
            except (OSError, ValueError):
                time.sleep(0.5)

    def is_enabled(self, name: str) -> bool:
        return self._enabled.get(name, False)


class PowerToysPlugin(Plugin):
    api: PublicAPI

    def __init__(self) -> None:
        self._settings = PowerToysSettings()
        self._icon_cache: dict[str, WoxImage] = {}
        # Cache of translations fetched from the host, keyed by i18n key.
        self._translations: dict[str, str] = {}

    async def init(self, ctx: Context, init_params: PluginInitParams) -> None:
        self.api = init_params.api
        self._settings.refresh()

    async def _t(self, ctx: Context, key: str) -> str:
        """Fetch a translation (cached); only needed where formatting or the
        raw text is required. Display-only strings use the ``i18n:`` prefix."""
        if key not in self._translations:
            self._translations[key] = await self.api.get_translation(ctx, key)
        return self._translations[key]

    def _enabled_actions(self) -> list[UtilityAction]:
        self._settings.refresh()
        actions: list[UtilityAction] = []
        for action in _ACTIONS:
            if action.open_settings_only:
                actions.append(action)
                continue
            enabled_name = action.settings_enabled_name or action.settings_link
            if self._settings.is_enabled(enabled_name):
                actions.append(action)
        return actions

    async def _make_result(self, ctx: Context, action: UtilityAction, score: float) -> Result:
        title = f"i18n:{action.title_key}"
        sub_title = f"{await self._t(ctx, 'keywords')}: {' '.join(action.keywords)}" if action.keywords else ""
        icon = _resolve_icon(action.icon, self._icon_cache)
        actions: list[ResultAction] = []
        if action.open_settings_only:
            actions.append(
                ResultAction(
                    name=title,
                    icon=icon,
                    is_default=True,
                    context_data={"op": "open_settings", "settings_link": action.settings_link},
                    action=self._on_action,
                )
            )
        else:
            actions.append(
                ResultAction(
                    name=title,
                    icon=icon,
                    is_default=True,
                    context_data={"op": "trigger", "event": action.event, "delayed": "1" if action.delayed else ""},
                    action=self._on_action,
                )
            )
            actions.append(
                ResultAction(
                    name="i18n:open_settings",
                    icon=icon,
                    context_data={"op": "open_settings", "settings_link": action.settings_link},
                    action=self._on_action,
                )
            )
            if action.admin_event:
                actions.append(
                    ResultAction(
                        name="i18n:run_as_administrator",
                        icon=icon,
                        context_data={"op": "trigger", "event": action.admin_event},
                        action=self._on_action,
                    )
                )
        return Result(title=title, sub_title=sub_title, icon=icon, score=score, actions=actions)

    async def _on_action(self, ctx: Context, ac: ActionContext) -> None:
        op = ac.context_data.get("op", "")
        if op == "trigger":
            if ac.context_data.get("delayed"):
                await asyncio.sleep(0.8)
            event = ac.context_data.get("event", "")
            if event and not _signal_event(event):
                await self.api.log(ctx, LogLevel.WARNING, f"failed to signal event: {event}")
        elif op == "open_settings":
            exe = _find_powertoys_exe()
            if not exe:
                await self.api.notify(ctx, await self._t(ctx, "powertoys_exe_not_found"))
                return
            subprocess.Popen([exe, f"--open-settings={ac.context_data.get('settings_link', '')}"])

    async def query(self, ctx: Context, query: Query) -> list[Result]:
        if not _is_powertoys_running():
            return [
                Result(
                    title="i18n:powertoys_not_running",
                    sub_title="i18n:powertoys_not_running_subtitle",
                    icon=WoxImage.new_relative("images/powertoys.png"),
                )
            ]
        actions = self._enabled_actions()
        search = (query.search or "").strip().lower()
        if search:
            terms = search.split()
            matched = [
                a
                for a in actions
                if all(any(term in keyword for keyword in a.keywords) for term in terms)
                or search in (await self._t(ctx, a.title_key)).lower()
            ]
        else:
            matched = actions
        # Decreasing base scores keep the original utility order; Wox's own
        # usage-based reordering still applies on top (no ignoreAutoScore).
        score = float(max(len(matched), 100))
        results: list[Result] = []
        for action in matched:
            results.append(await self._make_result(ctx, action, score))
            score -= 1.0
        return results


plugin = PowerToysPlugin()
