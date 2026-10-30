"""Turning mouse capture on or off in the running app.

Textual sets it once, when the app starts. Switching later uses its terminal driver's private
`_mouse` flag and `_enable_mouse_support` / `_disable_mouse_support` methods, which a Textual
upgrade may change or remove (tests/terminal/test_mouse.py checks them). When they're missing the switch
reports failure, and the choice applies from the next start.
"""

from textual.app import App

_METHODS = {True: "_enable_mouse_support", False: "_disable_mouse_support"}


def switch_mouse(app: App, on: bool) -> bool:
    """Returns whether mouse capture changed now."""
    driver = app._driver
    if driver is None or not hasattr(driver, "_mouse") or not callable(getattr(driver, _METHODS[on], None)):
        return False
    # The flag first when turning on (the method does nothing without it), last when turning off.
    if on:
        driver._mouse = True
    getattr(driver, _METHODS[on])()
    driver._mouse = on
    return True
