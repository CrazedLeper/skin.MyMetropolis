# MyMetropolis

Personal fork of [Metropolis](https://github.com/jingai/skin.metropolis), for
Kodi 21 (Omega). Original authors and license are retained.

## Current playlist improvements (4.2.1)

- The video playback queue shows the selected item's plot in the existing
  bottom synopsis panel, using Metropolis's fonts, position and scrolling rules.
- The queue menu has working **Sort by** and **Ascending/Descending** actions.
  Choose Title, Show / episode, or First aired. Show / episode groups shows
  alphabetically and orders their seasons and episodes numerically.
- Sorting changes the actual playback order. It uses Kodi's `Playlist.Swap`
  rather than clearing/rebuilding the queue, retaining entries and metadata.
  Missing show/date metadata stays at the end, and duplicate entries are kept.
- Turn Shuffle and Party Mode off before sorting. The sort preferences apply
  on request, not automatically when more items are queued. They reset when
  Kodi restarts. Music playlist controls retain their original behavior.

Kodi's video queue only exposes `SortByNone` internally. The custom buttons
therefore invoke a small bundled Python helper through Kodi's built-in Python
runtime. No additional helper add-on or external Python installation is needed.

## Install and check

This is a separate add-on, `skin.mymetropolis`, shown as **MyMetropolis**. The
original Metropolis remains available. Its preferences and custom home menus
are separate; they do not automatically transfer to the new skin.

1. In Kodi 21, install the supplied ZIP through **Settings > Add-ons > Install
   from zip file** (enable Unknown sources if Kodi asks).
2. Select **MyMetropolis** under **Settings > Interface > Skin**.
3. In Skin settings, enable **Auto-scroll text** if you want the plot to scroll,
   and leave **Hide plot** off. The panel follows the same options as source
   playlists. The selected item must have plot metadata in Kodi.
4. Queue a few episodes from a library playlist and open Current playlist.
   Verify that the bottom plot changes when the highlighted entry changes.
5. Press Left. Choose **Sort by**, select a method, and check the queue order.
   Use **Ascending/Descending** to reverse that method. Check a duplicate entry,
   a long plot, and the return from the menu to the list.
6. Test during playback: the playing item should continue while its queue
   position follows it. On a reported sorting failure, all items remain; check
   the order before trying again. Switch back to Metropolis at any time.

## Validation

Run `python3 -m unittest discover -s tests -v`. Automated checks cover sorting,
duplicate retention, 323-item reorder plans, missing metadata, asynchronous
swap sequencing, playing-item index retention in a simulated Kodi runtime,
queue-change detection, XML parsing and menu wiring.

These checks do not render Kodi or establish Fire TV runtime compatibility.
The installed skin still needs the on-device checks above.

References: Kodi Omega source in `xbmc/video/GUIViewStateVideo.cpp`,
`xbmc/interfaces/json-rpc/PlaylistOperations.cpp`, and `xbmc/PlayListPlayer.cpp`.
