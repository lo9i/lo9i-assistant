"""Lists the daemon pages (files, notifications) load a page at a time, as the web app's do."""

from dataclasses import replace

from textual.widgets import OptionList

from assistant_terminal.paging import PAGE_MAX, Pages
from assistant_terminal.tui.screens import FilesScreen, NotificationsScreen
from tests.terminal.conftest import wait_for


def _daemon(count: int) -> tuple[list[str], list[tuple[int, int]]]:
    return [f"i{n}" for n in range(count)], []


def _pages(items: list[str], asked: list[tuple[int, int]], size: int = 50) -> Pages[str]:
    async def load(offset: int, limit: int) -> list[str]:
        asked.append((offset, limit))
        return items[offset : offset + limit]

    return Pages(load, lambda item: item, size)


async def test_pages_load_one_after_another_until_the_end():
    items, asked = _daemon(120)
    pages = _pages(items, asked)
    assert len(await pages.reload()) == 50
    assert len(await pages.more()) == 50
    assert len(await pages.more()) == 20
    assert pages.done and await pages.more() == []
    assert asked == [(0, 50), (50, 50), (100, 50)]


async def test_loading_again_keeps_as_many_as_were_shown_in_pages_the_daemon_takes():
    items, asked = _daemon(3 * PAGE_MAX)
    pages = _pages(items, asked, size=PAGE_MAX)
    await pages.reload()
    await pages.more()
    asked.clear()
    assert len(await pages.reload()) == 2 * PAGE_MAX
    assert asked == [(0, PAGE_MAX), (PAGE_MAX, PAGE_MAX)]


async def test_an_item_that_comes_again_in_the_next_page_stays_where_it_was():
    items, asked = _daemon(100)
    pages = _pages(items, asked)
    await pages.reload()
    items.insert(0, "new")
    assert await pages.more() == items[51:100]
    assert pages.items == items[1:51] + items[51:100]


async def test_a_page_loading_while_the_list_loads_again_is_dropped():
    items, _ = _daemon(100)

    async def load(offset: int, limit: int) -> list[str]:
        if offset == 0:
            return items[:limit]
        await pages.reload()
        return ["late"]

    pages = Pages(load, lambda item: item)
    await pages.reload()
    assert await pages.more() == []
    assert "late" not in pages.items


async def test_files_load_the_next_page_as_the_list_is_scrolled(app, client):
    client.files.items = [replace(client.files.items[0], path=f"f{n}/a.txt", name=f"{n}.txt") for n in range(120)]
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/files", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, FilesScreen))
        options = app.screen.query_one("#files-list", OptionList)
        await wait_for(pilot, lambda: options.option_count == 50)
        assert client.files.pages == [(0, 50)]
        options.focus()
        await pilot.press("end")
        await wait_for(pilot, lambda: options.option_count == 100)
        await app.screen.reload()
        assert options.option_count == 100
        assert client.files.pages[-1] == (0, 100)


async def test_notifications_load_the_next_page_as_the_list_is_scrolled(app, client):
    first = client.notifications.items[0]
    client.notifications.items = [replace(first, id=f"n{n}", title=f"run {n}") for n in range(70)]
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/notifications", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, NotificationsScreen))
        options = app.screen.query_one("#notifications-list", OptionList)
        await wait_for(pilot, lambda: options.option_count == 50)
        await pilot.press("end")
        await wait_for(pilot, lambda: options.option_count == 70)
        assert client.notifications.pages[:2] == [(0, 50), (50, 50)]
