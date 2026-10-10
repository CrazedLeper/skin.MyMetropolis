"""Read-only synopsis lookup for the highlighted entry in the video queue."""

import json
import uuid

import xbmc
import xbmcgui

PREFIX = "MyMetropolis."
DETAILS = {
    "episode": ("VideoLibrary.GetEpisodeDetails", "episodeid", "episodedetails"),
    "movie": ("VideoLibrary.GetMovieDetails", "movieid", "moviedetails"),
    "musicvideo": ("VideoLibrary.GetMusicVideoDetails", "musicvideoid", "musicvideodetails"),
}


def rpc(method, params):
    response = json.loads(xbmc.executeJSONRPC(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
    })))
    if "error" in response:
        raise RuntimeError(response["error"].get("message", "Synopsis lookup failed"))
    return response.get("result", {})


def selected_item():
    # Use an explicit container so opening the left menu does not change which
    # item's labels are read. MyPlaylist.xml offers these three view controls.
    container = next((n for n in (55, 53, 57)
                      if xbmc.getCondVisibility("Control.IsVisible(%d)" % n)), 55)

    def label(name):
        return xbmc.getInfoLabel("Container(%d).ListItem.%s" % (container, name))

    return {
        "file": label("FileNameAndPath"), "type": label("DBTYPE").lower(),
        "id": label("DBID"), "plot": label("Plot"), "label": label("Label"),
    }


def item_key(item):
    return (item["file"], item["type"], item["id"], item["label"])


def lookup_plot(item):
    if item.get("plot", "").strip():
        return item["plot"]
    details = DETAILS.get(item.get("type"))
    try:
        database_id = int(item.get("id") or "0")
    except ValueError:
        database_id = 0
    if details and database_id > 0:
        method, id_name, result_name = details
        try:
            plot = rpc(method, {id_name: database_id, "properties": ["plot"]}).get(
                result_name, {}).get("plot", "")
            if plot.strip():
                return plot
        except RuntimeError as error:
            xbmc.log("MyMetropolis synopsis ID lookup: " + str(error), xbmc.LOGDEBUG)
    # Files.GetFileDetails(media=video) resolves the file against Kodi's video
    # library. This also covers queue entries that did not retain their DB ID.
    if item.get("file"):
        try:
            return rpc("Files.GetFileDetails", {
                "file": item["file"], "media": "video", "properties": ["plot"],
            }).get("filedetails", {}).get("plot", "")
        except RuntimeError as error:
            xbmc.log("MyMetropolis synopsis file lookup: " + str(error), xbmc.LOGDEBUG)
    return ""


def run():
    home = xbmcgui.Window(10000)
    monitor = xbmc.Monitor()
    session = uuid.uuid4().hex
    home.setProperty(PREFIX + "PlotSession", session)
    home.setProperty(PREFIX + "QueuePlot", "Loading synopsis...")
    previous = None
    cache = {}
    try:
        while (not monitor.abortRequested()
               and xbmc.getCondVisibility("Window.IsVisible(videoplaylist)")
               and home.getProperty(PREFIX + "PlotSession") == session):
            item = selected_item()
            key = item_key(item)
            if key != previous:
                home.setProperty(PREFIX + "QueuePlot", "Loading synopsis...")
                # Wait briefly for rapid scrolling to settle before a library query.
                if monitor.waitForAbort(0.15):
                    break
                if item_key(selected_item()) != key:
                    continue
                if item.get("plot", "").strip():
                    plot = item["plot"]
                elif key in cache:
                    plot = cache[key]
                else:
                    plot = lookup_plot(item)
                    cache[key] = plot
                # A network-backed file lookup can finish after selection changed.
                if (item_key(selected_item()) == key
                        and home.getProperty(PREFIX + "PlotSession") == session):
                    home.setProperty(PREFIX + "QueuePlot", plot or
                                     "No synopsis available for this queued item.")
                    previous = key
            if monitor.waitForAbort(0.2):
                break
    except Exception as error:
        xbmc.log("MyMetropolis synopsis helper: " + str(error), xbmc.LOGERROR)
        if home.getProperty(PREFIX + "PlotSession") == session:
            home.setProperty(PREFIX + "QueuePlot", "Synopsis lookup failed. See Kodi log.")
    finally:
        # Never clear a newer instance's text after a quick leave/re-enter.
        if home.getProperty(PREFIX + "PlotSession") == session:
            home.clearProperty(PREFIX + "PlotSession")


if __name__ == "__main__":
    run()
