"""Manual episode identification for MyMetropolis, Kodi 19+ (Python 3).

Uses the installed TMDb TV scraper's public application configuration.
Updates this Kodi library only. No video files or sidecar NFOs are changed.
"""
import ast
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

HEADING = "Identify episode"
SCRAPER = "metadata.tvshows.themoviedb.org.python"
BACKUPS = "special://profile/addon_data/skin.mymetropolis/episode-identification/"
FIELDS = ["title", "plot", "season", "episode", "firstaired", "director",
          "writer", "productioncode", "art", "uniqueid", "ratings"]


def rpc(method, **params):
    response = json.loads(xbmc.executeJSONRPC(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params})))
    if "error" in response:
        raise RuntimeError("Kodi could not complete " + method +
                           ": " + response["error"].get("message", "unknown error"))
    return response["result"]


def read_json(path):
    if not xbmcvfs.exists(path):
        return None
    handle = xbmcvfs.File(path)
    try:
        return json.loads(handle.read())
    finally:
        handle.close()


def write_json(path, data):
    handle = xbmcvfs.File(path, "w")
    try:
        if not handle.write(json.dumps(data, ensure_ascii=False, indent=2)):
            raise RuntimeError("Could not save the previous metadata; no update was made.")
    finally:
        handle.close()


def scraper_key():
    try:
        addon = xbmcaddon.Addon(SCRAPER)
    except RuntimeError:
        raise RuntimeError("Install The Movie Database TV Shows scraper from "
                           "Kodi's add-on repository, then try Identify episode again.")
    path = os.path.join(addon.getAddonInfo("path"), "libs", "settings.py")
    handle = xbmcvfs.File(path)
    try:
        tree = ast.parse(handle.read())
    finally:
        handle.close()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "TMDB_CLOWNCAR"
                for target in node.targets):
            key = ast.literal_eval(node.value)
            if isinstance(key, str) and key:
                return key
    raise RuntimeError("This TMDb scraper version has a different configuration. "
                       "No library changes were made.")


class TMDb:
    def __init__(self):
        self.key = scraper_key()

    def get(self, path, **params):
        params.update(api_key=self.key, language="en-US")
        request = Request("https://api.themoviedb.org/3/" + path + "?" +
                          urlencode(params), headers={
                              "Accept": "application/json",
                              "User-Agent": "MyMetropolis episode identification"})
        progress = xbmcgui.DialogProgress()
        progress.create(HEADING, "Loading candidates from TMDb...")
        try:
            with urlopen(request, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
            if progress.iscanceled():
                raise Cancelled()
            return data
        except HTTPError as error:
            raise RuntimeError("TMDb returned HTTP " + str(error.code) +
                               ". Try again later; no library changes were made.")
        except URLError:
            raise RuntimeError("Cannot reach TMDb. Check your internet connection.")
        finally:
            progress.close()


class Cancelled(Exception):
    pass


def choose(heading, values, labels, selected=-1):
    if not values:
        xbmcgui.Dialog().ok(HEADING, "No matching candidates were found.")
        raise Cancelled()
    index = xbmcgui.Dialog().select(heading, labels, preselect=selected)
    if index < 0:
        raise Cancelled()
    return values[index]


def resolve_show(api, show):
    ids = show.get("uniqueid", {})
    if str(ids.get("tmdb", "")).isdigit():
        return api.get("tv/" + str(ids["tmdb"]))
    for kind, source in (("tvdb", "tvdb_id"), ("imdb", "imdb_id")):
        if ids.get(kind):
            candidates = api.get("find/" + str(ids[kind]),
                                 external_source=source).get("tv_results", [])
            if len(candidates) == 1:
                return api.get("tv/" + str(candidates[0]["id"]))
    # Resolve the existing parent series, never silently reparent one episode.
    query = xbmcgui.Dialog().input("Find this series on TMDb", show["title"])
    if not query.strip():
        raise Cancelled()
    candidates = api.get("search/tv", query=query.strip()).get("results", [])
    candidate = choose("Select the existing series: " + show["title"], candidates,
                       [item["name"] + " (" + item.get("first_air_date", "")[:4] + ")"
                        for item in candidates])
    if not xbmcgui.Dialog().yesno(HEADING,
            "Use " + candidate["name"] + " for the existing series " +
            show["title"] + "?\nIf the entire series was scraped incorrectly, "
            "cancel and refresh the series itself first."):
        raise Cancelled()
    return api.get("tv/" + str(candidate["id"]))


def episode_params(episodeid, item):
    credits = item.get("credits", {}).get("crew", [])
    still = item.get("still_path")
    return {
        "episodeid": episodeid,
        "title": item.get("name", ""),
        "plot": item.get("overview") or "",
        "season": int(item["season_number"]),
        "episode": int(item["episode_number"]),
        "firstaired": item.get("air_date") or "",
        "productioncode": item.get("production_code") or "",
        "director": sorted({p["name"] for p in credits if p.get("job") == "Director"}),
        "writer": sorted({p["name"] for p in credits
                          if p.get("job") in ("Writer", "Screenplay", "Teleplay", "Story")}),
        "art": {"thumb": "https://image.tmdb.org/t/p/original" + still if still else ""},
        "uniqueid": {"tmdb": str(item["id"])},
        "ratings": {"themoviedb": {"rating": float(item.get("vote_average") or 0),
                                 "votes": int(item.get("vote_count") or 0),
                                 "default": True}},
    }


def old_params(episodeid, episode):
    result = {"episodeid": episodeid}
    for key in FIELDS:
        if key in episode:
            result[key] = episode[key]
    return result


def apply(episodeid, original, params):
    # Save a unique backup before each update. A failed backup blocks the update.
    if not xbmcvfs.exists(BACKUPS) and not xbmcvfs.mkdirs(BACKUPS):
        raise RuntimeError("Could not create the metadata backup folder.")
    path = BACKUPS + str(episodeid) + "-" + str(time.time_ns()) + ".json"
    backup = {"file": original["file"], "before": old_params(episodeid, original),
              "after": params}
    write_json(path, backup)
    rpc("VideoLibrary.SetEpisodeDetails", **params)
    # Mark latest only after Kodi accepted the new metadata.
    try:
        write_json(BACKUPS + str(episodeid) + "-latest.json", backup)
    except Exception:
        xbmcgui.Dialog().ok(HEADING, "Metadata was updated. The backup is saved, "
                            "but the Undo shortcut could not be recorded.")
    xbmc.executebuiltin("Dialog.Close(videoinfo)")
    xbmc.executebuiltin("Container.Refresh")
    xbmcgui.Dialog().notification(HEADING, "Episode metadata updated",
                                 xbmcgui.NOTIFICATION_INFO)


def main():
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        raise RuntimeError("Open Identify episode from an episode in your Kodi library.")
    episodeid = int(sys.argv[1])
    original = rpc("VideoLibrary.GetEpisodeDetails", episodeid=episodeid,
                   properties=FIELDS + ["file", "tvshowid", "showtitle"])["episodedetails"]
    if xbmc.getCondVisibility("Library.IsScanningVideo"):
        raise RuntimeError("Wait for the library scan to finish, then try again.")
    backup = read_json(BACKUPS + str(episodeid) + "-latest.json")
    if backup and backup.get("file") == original["file"]:
        action = choose(HEADING, ["identify", "undo"],
                        ["Find the correct episode", "Undo the last identification"])
        if action == "undo":
            previous = backup["before"]
            if xbmcgui.Dialog().yesno(HEADING, "Restore the previous match: " +
                                     previous.get("title", "") + "?"):
                apply(episodeid, original, previous)
            return
    show = rpc("VideoLibrary.GetTVShowDetails", tvshowid=original["tvshowid"],
               properties=["uniqueid"])["tvshowdetails"]
    api = TMDb()
    matched_show = resolve_show(api, show)
    seasons = matched_show.get("seasons", [])
    current = next((i for i, season in enumerate(seasons)
                    if season["season_number"] == original.get("season")), -1)
    season = choose("Choose season: " + matched_show["name"], seasons,
                    ["Season " + str(s["season_number"]) + " — " +
                     s.get("name", "") for s in seasons], current)
    episodes = api.get("tv/{}/season/{}".format(
        matched_show["id"], season["season_number"])).get("episodes", [])
    while True:
        options = [None] + episodes
        labels = ["Search these episodes by title..."] + [
            "S{:02d}E{:02d} — {} ({})".format(
                e["season_number"], e["episode_number"], e.get("name", ""),
                e.get("air_date") or "date unknown") for e in episodes]
        selected = choose("Choose the correct episode", options, labels)
        if selected is not None:
            break
        query = xbmcgui.Dialog().input("Episode title (blank shows all)")
        all_episodes = api.get("tv/{}/season/{}".format(
            matched_show["id"], season["season_number"])).get("episodes", [])
        episodes = [e for e in all_episodes
                    if query.casefold() in e.get("name", "").casefold()]
    detail = api.get("tv/{}/season/{}/episode/{}".format(
        matched_show["id"], selected["season_number"], selected["episode_number"]),
        append_to_response="credits")
    description = "{}\nS{:02d}E{:02d} — {}\n\n{}\n\nReplace metadata for:\n{}".format(
        matched_show["name"], detail["season_number"], detail["episode_number"],
        detail["name"], detail.get("overview") or "No synopsis available.",
        os.path.basename(original["file"]))
    if not xbmcgui.Dialog().yesno("Apply this match?", description,
                                 yeslabel="Apply match", nolabel="Cancel"):
        return
    # Re-check the target just before applying; scans can invalidate database IDs.
    latest = rpc("VideoLibrary.GetEpisodeDetails", episodeid=episodeid,
                 properties=FIELDS + ["file"])["episodedetails"]
    if latest["file"] != original["file"] or xbmc.getCondVisibility("Library.IsScanningVideo"):
        raise RuntimeError("The library changed during selection. Try again.")
    apply(episodeid, latest, episode_params(episodeid, detail))


if __name__ == "__main__":
    try:
        main()
    except Cancelled:
        pass
    except Exception as error:
        # Never log request URLs: they include scraper application credentials.
        xbmcgui.Dialog().ok(HEADING, str(error))
