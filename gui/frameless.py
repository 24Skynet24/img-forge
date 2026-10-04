"""Native Windows glue for the frameless main window.

Qt draws no frame (the window has its own title bar), but the window keeps the native
behaviour: edge resizing, Aero Snap, drag by the title bar, maximize by double-click.
That is done by answering ``WM_NCHITTEST`` and removing the non-client area in ``WM_NCCALCSIZE``.
On other platforms (and in tests) every function is a no-op and Qt's own handling applies.
"""
from __future__ import annotations

import contextlib
import sys
from collections.abc import Callable

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QWidget

IS_WINDOWS = sys.platform == "win32"

WM_NCCALCSIZE, WM_NCHITTEST = 0x0083, 0x0084
HTCLIENT, HTCAPTION = 1, 2
HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT, HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 10, 11, 12, 13, 14, 15, 16, 17
EDGE = 8  # px of the resize border (logical)
CORNER = 16  # px of the corner grip along each edge

_GWL_STYLE = -16
_WS_THICKFRAME, _WS_MINIMIZEBOX, _WS_MAXIMIZEBOX, _WS_CAPTION = 0x00040000, 0x00020000, 0x00010000, 0x00C00000
_SWP_FLAGS = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020  # NOSIZE | NOMOVE | NOZORDER | NOACTIVATE | FRAMECHANGED
_SM_CXSIZEFRAME, _SM_CYSIZEFRAME, _SM_CXPADDEDBORDER = 32, 33, 92
WVR_REDRAW = 0x0300  # WVR_HREDRAW | WVR_VREDRAW: do not copy old client bits, repaint everything


def hit_test(
    pos: QPoint, size: tuple[int, int], maximized: bool, in_caption: Callable[[QPoint], bool]
) -> int:
    """Windows hit-test code for ``pos`` (window coordinates) in a frameless window of ``size``."""
    width, height = size
    if not maximized:
        left, right = pos.x() < EDGE, pos.x() >= width - EDGE
        top, bottom = pos.y() < EDGE, pos.y() >= height - EDGE
        near_left, near_right = pos.x() < CORNER, pos.x() >= width - CORNER
        near_top, near_bottom = pos.y() < CORNER, pos.y() >= height - CORNER
        # corners are a larger target than the edges: much easier to grab
        if (top and near_left) or (left and near_top):
            return HTTOPLEFT
        if (top and near_right) or (right and near_top):
            return HTTOPRIGHT
        if (bottom and near_left) or (left and near_bottom):
            return HTBOTTOMLEFT
        if (bottom and near_right) or (right and near_bottom):
            return HTBOTTOMRIGHT
        if left:
            return HTLEFT
        if right:
            return HTRIGHT
        if top:
            return HTTOP
        if bottom:
            return HTBOTTOM
    return HTCAPTION if in_caption(pos) else HTCLIENT


def enable_native_frame(window: QWidget) -> None:
    """Give the frameless HWND the styles that make native resize / snap / minimize work."""
    if not IS_WINDOWS:
        return
    import ctypes

    user32 = ctypes.windll.user32
    hwnd = int(window.winId())
    get = user32.GetWindowLongPtrW if hasattr(user32, "GetWindowLongPtrW") else user32.GetWindowLongW
    set_ = user32.SetWindowLongPtrW if hasattr(user32, "SetWindowLongPtrW") else user32.SetWindowLongW
    get.restype = ctypes.c_ssize_t
    set_.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    style = get(ctypes.c_void_p(hwnd), _GWL_STYLE)
    wanted = style | _WS_THICKFRAME | _WS_MINIMIZEBOX | _WS_MAXIMIZEBOX | _WS_CAPTION
    if wanted != style:
        set_(ctypes.c_void_p(hwnd), _GWL_STYLE, wanted)
        user32.SetWindowPos(ctypes.c_void_p(hwnd), None, 0, 0, 0, 0, _SWP_FLAGS)
    _enable_shadow(hwnd)


def _enable_shadow(hwnd: int) -> None:
    """Give the borderless window the normal DWM drop shadow (1 px of extended frame is enough)."""
    import ctypes
    from ctypes import wintypes

    class Margins(ctypes.Structure):
        _fields_ = [(name, wintypes.INT) for name in ("left", "right", "top", "bottom")]

    # no DWM (very old Windows / remote session): the shadow is cosmetic
    with contextlib.suppress(OSError, AttributeError):
        ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(ctypes.c_void_p(hwnd), ctypes.byref(Margins(0, 0, 0, 1)))


def handle_native_event(
    window: QWidget, message: object, in_caption: Callable[[QPoint], bool]
) -> tuple[bool, int] | None:
    """Answer ``WM_NCHITTEST`` / ``WM_NCCALCSIZE``; returns ``(handled, result)`` or None to pass on."""
    if not IS_WINDOWS:
        return None
    import ctypes
    from ctypes import wintypes

    msg = wintypes.MSG.from_address(int(message))  # type: ignore[call-overload]
    if msg.message == WM_NCHITTEST:
        x = ctypes.c_short(msg.lParam & 0xFFFF).value
        y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
        ratio = window.devicePixelRatioF()
        pos = window.mapFromGlobal(QPoint(round(x / ratio), round(y / ratio)))
        code = hit_test(pos, (window.width(), window.height()), window.isMaximized(), in_caption)
        return (True, code) if code != HTCLIENT else None
    if msg.message == WM_NCCALCSIZE and msg.wParam:
        if window.isMaximized():
            # A maximised window overhangs the screen by its (invisible) sizing frame: pull it back in.
            user32 = ctypes.windll.user32

            class Params(ctypes.Structure):
                _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]

            params = Params.from_address(msg.lParam)
            fx = user32.GetSystemMetrics(_SM_CXSIZEFRAME) + user32.GetSystemMetrics(_SM_CXPADDEDBORDER)
            fy = user32.GetSystemMetrics(_SM_CYSIZEFRAME) + user32.GetSystemMetrics(_SM_CXPADDEDBORDER)
            rect = params.rgrc[0]
            rect.left += fx
            rect.top += fy
            rect.right -= fx
            rect.bottom -= fy
            return True, 0
        return True, WVR_REDRAW
    return None
