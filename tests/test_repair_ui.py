import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.repair_page import RepairPage  # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


def test_repair_page_builds_with_four_tabs_and_seven_steps():
    _app()
    page = RepairPage(lambda: None)
    assert page.tabs.count() == 4
    assert page.steps_list.count() == 7


def test_destructive_step_shows_locked_in_recovery():
    _app()
    page = RepairPage(lambda: None)
    page._mode = "recovery"
    page._refresh_steps()
    last = page.steps_list.item(page.steps_list.count() - 1).text()
    assert "terkunci" in last
    page._done.update({"charge_restart", "wipe_cache", "sideload_ota"})
    page._refresh_steps()
    last = page.steps_list.item(page.steps_list.count() - 1).text()
    assert "siap" in last
