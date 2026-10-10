import copy
import importlib.util
from pathlib import Path
import random
import sys
import types
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.modules.setdefault("xbmc", types.ModuleType("xbmc"))
sys.modules.setdefault("xbmcgui", types.ModuleType("xbmcgui"))
spec = importlib.util.spec_from_file_location("playlist_sort", ROOT / "extras/playlist_sort.py")
sorter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sorter)


def item(label, **fields):
    return dict(label=label, title=label, type="episode", file="/videos/" + label, **fields)


class SortTests(unittest.TestCase):
    def test_natural_titles_and_stable_duplicates(self):
        items = [item("Episode 10"), item("Episode 2"), item("episode 2"), item("Alpha")]
        self.assertEqual(sorter.sorted_indices(items, 0), [3, 1, 2, 0])
        self.assertEqual(sorter.sorted_indices(items, 0, True), [0, 1, 2, 3])

    def test_chronological_episode_order_and_missing_metadata(self):
        items = [item("B", showtitle="Voyager", season=2, episode=1),
                 item("A", showtitle="Voyager", season=1, episode=10),
                 item("C", showtitle="Voyager", season=1, episode=2), item("Movie")]
        self.assertEqual(sorter.sorted_indices(items, 1), [2, 1, 0, 3])
        self.assertEqual(sorter.sorted_indices(items, 1, True), [0, 1, 2, 3])

    def test_aired_dates_and_missing_dates_in_both_directions(self):
        items = [item("Unknown"), item("New", firstaired="2020-01-01"),
                 item("Old", firstaired="1994-09-09"), item("Movie", premiered="2000-01-01")]
        self.assertEqual(sorter.sorted_indices(items, 2), [2, 3, 1, 0])
        self.assertEqual(sorter.sorted_indices(items, 2, True), [1, 3, 2, 0])

    def test_swap_plan_permutations_including_323_item_queue(self):
        rng = random.Random(42)
        for size in [0, 1, 2, 10, 323]:
            for _ in range(20):
                desired = list(range(size))
                rng.shuffle(desired)
                actual = list(range(size))
                swaps = list(sorter.swap_plan(desired))
                self.assertLessEqual(len(swaps), max(0, size - 1))
                for first, second in swaps:
                    actual[first], actual[second] = actual[second], actual[first]
                self.assertEqual(actual, desired)

    def test_async_swaps_preserve_metadata_duplicates_and_current_item(self):
        originals = [item("Z", plot="Plot Z", resume={"position": 85}),
                     item("A", plot="Plot A"), item("A", plot="Plot A")]
        queue = copy.deepcopy(originals)
        playing = [0]
        pending = []
        calls = []

        def rpc(method, params=None):
            calls.append(method)
            if method == "Playlist.GetItems":
                if pending:
                    first, second = pending.pop()
                    queue[first], queue[second] = queue[second], queue[first]
                    if playing[0] == first:
                        playing[0] = second
                    elif playing[0] == second:
                        playing[0] = first
                return {"items": copy.deepcopy(queue)}
            self.assertEqual(method, "Playlist.Swap")
            self.assertFalse(pending, "Must finish each asynchronous swap first")
            pending.append((params["position1"], params["position2"]))
            return "OK"

        with patch.object(sorter, "rpc", side_effect=rpc), \
                patch.object(sorter, "queue_is_shuffled", return_value=False):
            sorter.apply_order(originals, sorter.sorted_indices(originals, 0), Mock(iscanceled=lambda: False),
                               Mock(abortRequested=lambda: False))
        self.assertEqual(queue, [originals[1], originals[2], originals[0]])
        self.assertEqual(queue[playing[0]], originals[0])
        self.assertEqual(set(calls), {"Playlist.GetItems", "Playlist.Swap"})

    def test_changed_queue_before_start_does_not_mutate(self):
        with patch.object(sorter, "get_items", return_value=[item("Changed")]), \
                patch.object(sorter, "rpc") as rpc:
            with self.assertRaisesRegex(RuntimeError, "queue changed"):
                sorter.apply_order([item("Z"), item("A")], [1, 0], Mock(), Mock())
            rpc.assert_not_called()

    def test_shuffle_during_sort_stops_before_swapping(self):
        items = [item("Z"), item("A")]
        with patch.object(sorter, "get_items", return_value=items), \
                patch.object(sorter, "queue_is_shuffled", return_value=True), \
                patch.object(sorter, "rpc") as rpc:
            with self.assertRaisesRegex(RuntimeError, "Shuffle"):
                sorter.apply_order(items, [1, 0], Mock(iscanceled=lambda: False), Mock(abortRequested=lambda: False))
            rpc.assert_not_called()

    def test_shuffle_checks_video_even_if_audio_is_playing(self):
        with patch.object(sorter.xbmc, "getInfoLabel", create=True, return_value="On") as info, \
                patch.object(sorter.xbmc, "getLocalizedString", create=True, return_value="On"):
            self.assertTrue(sorter.queue_is_shuffled())
            info.assert_called_once_with("Playlist.Random(video)")


class SkinTests(unittest.TestCase):
    def test_queue_has_dedicated_scrolling_plot_panel(self):
        playlist = ET.parse(ROOT / "720p/MyPlaylist.xml")
        self.assertIsNotNone(playlist.find(".//include[.='MyMetropolisQueuePlot']"))
        self.assertTrue(any("playlist_plot.py" in (c.text or "")
                            for c in playlist.findall("onload")))
        includes = ET.parse(ROOT / "720p/Includes_MyMetropolis.xml")
        plot = includes.find(".//include[@name='MyMetropolisQueuePlot']")
        for box in plot.findall(".//control[@type='textbox']"):
            self.assertIn("MyMetropolis.QueuePlot", box.findtext("label"))
            self.assertEqual(box.findtext("autoscroll"), "true")

    def test_custom_sort_buttons_bypass_native_sort_ids(self):
        menus = ET.parse(ROOT / "720p/Includes_MyMetropolis.xml")
        buttons = menus.findall(".//control[@type='button']")
        self.assertEqual([b.get("id") for b in buttons], ["7301", "7302"])
        for button in buttons:
            self.assertEqual(button.findtext("visible"), "Window.IsActive(videoplaylist)")
            self.assertIn("playlist_sort.py", button.findtext("onclick"))
        includes = ET.parse(ROOT / "720p/Includes.xml")
        for identifier in ["3", "4"]:
            control = includes.find(".//control[@id='" + identifier + "']")
            self.assertEqual(control.findtext("visible"), "!Window.IsActive(videoplaylist)")

    def test_installs_as_distinct_skin_with_existing_includes(self):
        addon = ET.parse(ROOT / "addon.xml").getroot()
        self.assertEqual(addon.get("id"), "skin.mymetropolis")
        self.assertEqual(addon.get("name"), "MyMetropolis")
        for xml in (ROOT / "720p").glob("*.xml"):
            ET.parse(xml)
        includes = ET.parse(ROOT / "720p/Includes.xml")
        for include in includes.findall("include[@file]"):
            self.assertTrue((ROOT / "720p" / include.get("file")).exists())


if __name__ == "__main__":
    unittest.main()
