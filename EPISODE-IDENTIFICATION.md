# Manual episode identification

On an episode's information page, the second circular button is now
**Identify episode**. Movie, series, and music-video Refresh controls keep
Kodi's existing behavior.

1. Choose the correct season from TMDb.
2. Choose an episode by number and title, or search titles within that season.
3. Review the synopsis and selected filename, then choose **Apply match**.

The helper updates title, plot, season/episode number, air date, thumbnail,
director/writer, production code, rating, and episode ID in the current Kodi
library. It leaves the file path, media runtime, watched status, resume position,
and the parent series unchanged. Kodi's SetEpisodeDetails API does not expose
cast editing; the existing cast remains.

If the series has no recognized TMDb/TVDB/IMDb ID, the helper asks you to search
and select the existing series on TMDb. If the whole series is incorrect, cancel
and use Kodi's native Refresh on the series information page first.

## Requirements

- MyMetropolis and Kodi 19 or newer, with Python 3.
- The Movie Database TV Shows scraper
  (metadata.tvshows.themoviedb.org.python) installed from Kodi's repository.
- Internet access to TMDb. There is no separate API-key setup.

The helper reads the installed scraper's public application configuration
without executing its code. It fails clearly if that configuration changes.
Candidate metadata uses TMDb's standard episode order and English text.

## Backups and persistence

Every update saves the previous metadata under:

special://profile/addon_data/skin.mymetropolis/episode-identification/

On subsequent visits, Identify episode offers **Undo the last identification**.
Undo also makes a backup, so it can be reversed.

Changes affect this Kodi library only. No video or NFO files are written.
Removing/reimporting an episode, switching skins and using native Refresh,
or refreshing an entire series may replace the correction. For a correction
that survives rebuilding the library, fix file numbering or export verified
episode NFO metadata separately.

Combined multi-episode files need proper multi-episode naming/NFO handling;
this picker applies one episode record at a time.

## Installation

Apply this branch to the full skin repository. Deploy these two changed files
to the installed skin on the Fire TV and reload Kodi's skin:

- 720p/DialogVideoInfo.xml
- resources/identify_episode.py

The other files in this change document and test the implementation.
This source checkout is not a complete skin installation ZIP.

## Validation

Run: python3 -m unittest discover -s tests -v

Tests cover correct metadata assignment, cancellation, confirmation rejection,
backup failure, Undo, database-ID reuse, active scans, and absent thumbnails.
XML parsing and button wiring are also checked during development.
Live navigation, network queries, and metadata writes still require a Kodi
test on the target device.

Data attribution: metadata and images supplied by The Movie Database (TMDb).
This feature uses the TMDb API but is not endorsed or certified by TMDb.
