"""Sort the existing Kodi video queue using in-place swaps, never clear/add."""

import json
import re
import sys
import time

import xbmc
import xbmcgui

PLAYLIST_ID = 1
PREFIX = "MyMetropolis."
METHODS = ("Title", "Show / episode", "First aired")
FIELDS = ["file", "title", "showtitle", "season", "episode", "firstaired", "premiered"]


def rpc(method, params=None):
    request = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    response = json.loads(xbmc.executeJSONRPC(json.dumps(request)))
    if "error" in response:
        raise RuntimeError(response["error"].get("message", "Kodi request failed"))
    return response.get("result", {})


def get_items(properties=FIELDS):
    # Explicitly request the physical queue order, rather than a sorted RPC view.
    return rpc("Playlist.GetItems", {
        "playlistid": PLAYLIST_ID, "properties": properties,
        "sort": {"method": "none"},
    }).get("items", [])


def identity(item):
    return (item.get("type"), item.get("id"), item.get("file"), item.get("label"))


def natural(value):
    """Case-insensitive text with numeric portions ordered as numbers."""
    return tuple((1, int(part)) if part.isdigit() else (0, part.casefold())
                 for part in re.split(r"(\d+)", str(value or "")))


def number(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def title(item):
    return natural(item.get("title") or item.get("label") or item.get("file"))


def sort_key(item, method):
    if method == 1:
        return (natural(item.get("showtitle")), number(item.get("season")),
                number(item.get("episode")), title(item))
    if method == 2:
        return (item.get("firstaired") or item.get("premiered") or "", title(item))
    return title(item)


def missing(item, method):
    if method == 1:
        return not item.get("showtitle") or number(item.get("episode")) < 0
    if method == 2:
        return not (item.get("firstaired") or item.get("premiered"))
    return False


def sorted_indices(items, method, reverse=False):
    # Python's stable sort retains the order of equal keys and duplicate entries.
    known = [i for i, item in enumerate(items) if not missing(item, method)]
    unknown = [i for i, item in enumerate(items) if missing(item, method)]
    known.sort(key=lambda i: sort_key(items[i], method), reverse=reverse)
    return known + unknown  # Missing metadata stays at the end in either direction.


def swap_plan(order):
    """Return at most n-1 swaps, treating duplicate queue entries separately."""
    current = list(range(len(order)))
    positions = list(range(len(order)))
    for destination, original in enumerate(order):
        source = positions[original]
        if destination == source:
            continue
        displaced = current[destination]
        current[destination], current[source] = original, displaced
        positions[original], positions[displaced] = destination, source
        yield destination, source


def queue_is_shuffled():
    # Explicit video queue: the current player may instead be playing music.
    return xbmc.getInfoLabel("Playlist.Random(video)") == xbmc.getLocalizedString(16041)


def apply_order(items, order, progress, monitor):
    expected = [identity(item) for item in items]
    if [identity(item) for item in get_items(["file"])] != expected:
        raise RuntimeError("The queue changed. Please sort again.")
    swaps = list(swap_plan(order))
    for step, (first, second) in enumerate(swaps):
        if progress.iscanceled():
            raise RuntimeError("Sorting cancelled; all entries remain, partly reordered.")
        if monitor.abortRequested():
            raise RuntimeError("Kodi is closing; sorting stopped.")
        if queue_is_shuffled():
            raise RuntimeError("Shuffle was enabled; sorting stopped.")
        rpc("Playlist.Swap", {
            "playlistid": PLAYLIST_ID, "position1": first, "position2": second,
        })
        expected[first], expected[second] = expected[second], expected[first]
        # Swap is posted asynchronously by Kodi. Observe its completion before
        # submitting another swap so a failure cannot scramble subsequent steps.
        deadline = time.monotonic() + 5
        while [identity(item) for item in get_items(["file"])] != expected:
            if time.monotonic() >= deadline or monitor.waitForAbort(0.05):
                raise RuntimeError("The queue changed or Kodi did not finish a swap. "
                                   "Sorting stopped; all entries remain in the queue.")
        progress.update(int(100 * (step + 1) / max(1, len(swaps))))
    if [identity(item) for item in get_items(["file"])] != expected:
        raise RuntimeError("The queue changed while sorting. Please check its order.")


def initialize(home):
    if not home.getProperty(PREFIX + "SortMethod"):
        home.setProperty(PREFIX + "SortMethod", "0")
    if not home.getProperty(PREFIX + "SortReverse"):
        home.setProperty(PREFIX + "SortReverse", "false")
    home.setProperty(PREFIX + "SortMethodLabel",
                     METHODS[int(home.getProperty(PREFIX + "SortMethod"))])
    home.setProperty(PREFIX + "SortOrderLabel", xbmc.getLocalizedString(
        585 if home.getProperty(PREFIX + "SortReverse") == "true" else 584))


def main(action):
    home = xbmcgui.Window(10000)
    initialize(home)
    if action == "init" or home.getProperty(PREFIX + "SortBusy"):
        return
    home.setProperty(PREFIX + "SortBusy", "true")
    progress = None
    try:
        if xbmc.getCondVisibility("PartyMode.Enabled") or queue_is_shuffled():
            xbmcgui.Dialog().ok("MyMetropolis", "Turn Shuffle and Party Mode off before sorting.")
            return
        method = int(home.getProperty(PREFIX + "SortMethod"))
        reverse = home.getProperty(PREFIX + "SortReverse") == "true"
        if action == "choose":
            method = xbmcgui.Dialog().select("Sort current playlist by", list(METHODS),
                                           preselect=method)
            if method < 0:
                return
        elif action == "direction":
            reverse = not reverse
        else:
            return
        items = get_items()
        if len(items) < 2:
            xbmcgui.Dialog().notification("MyMetropolis", "Queue needs at least two items.")
            return
        order = sorted_indices(items, method, reverse)
        progress = xbmcgui.DialogProgress()
        progress.create("Sorting current playlist", "Keeping all queued items and their metadata.")
        apply_order(items, order, progress, xbmc.Monitor())
        home.setProperty(PREFIX + "SortMethod", str(method))
        home.setProperty(PREFIX + "SortReverse", "true" if reverse else "false")
        initialize(home)
    except Exception as error:
        xbmc.log("MyMetropolis playlist sorting: " + str(error), xbmc.LOGERROR)
        if progress is not None:
            progress.close()
            progress = None
        xbmcgui.Dialog().ok("Playlist sorting stopped", str(error))
    finally:
        if progress is not None:
            progress.close()
        home.clearProperty(PREFIX + "SortBusy")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "choose")
