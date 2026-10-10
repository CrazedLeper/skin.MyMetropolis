import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.modules.setdefault("xbmc", types.ModuleType("xbmc"))
sys.modules.setdefault("xbmcgui", types.ModuleType("xbmcgui"))
spec = importlib.util.spec_from_file_location("playlist_plot", ROOT / "extras/playlist_plot.py")
plotter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plotter)


class PlotTests(unittest.TestCase):
    def test_native_plot_needs_no_library_calls(self):
        with patch.object(plotter, "rpc") as rpc:
            self.assertEqual(plotter.lookup_plot({"plot": "Native synopsis"}), "Native synopsis")
            rpc.assert_not_called()

    def test_missing_queue_plot_uses_episode_library_record(self):
        with patch.object(plotter, "rpc", return_value={"episodedetails": {"plot": "Library plot"}}) as rpc:
            self.assertEqual(plotter.lookup_plot({"type": "episode", "id": "123", "file": "/episode"}),
                             "Library plot")
            rpc.assert_called_once_with("VideoLibrary.GetEpisodeDetails",
                                        {"episodeid": 123, "properties": ["plot"]})

    def test_no_database_id_resolves_video_path(self):
        with patch.object(plotter, "rpc", return_value={"filedetails": {"plot": "File plot"}}) as rpc:
            self.assertEqual(plotter.lookup_plot({"id": "", "type": "", "file": "smb://media/file.mkv"}),
                             "File plot")
            rpc.assert_called_once_with("Files.GetFileDetails", {
                "file": "smb://media/file.mkv", "media": "video", "properties": ["plot"]})

    def test_empty_library_plot_falls_back_to_file(self):
        with patch.object(plotter, "rpc", side_effect=[{"moviedetails": {"plot": ""}},
                                                     {"filedetails": {"plot": "Fallback"}}]):
            self.assertEqual(plotter.lookup_plot({"type": "movie", "id": "12", "file": "/movie"}),
                             "Fallback")

    def test_unresolvable_path_returns_empty_without_mutation(self):
        with patch.object(plotter, "rpc", side_effect=RuntimeError("Not in library")), \
                patch.object(plotter.xbmc, "log", create=True), \
                patch.object(plotter.xbmc, "LOGDEBUG", create=True, new=0):
            self.assertEqual(plotter.lookup_plot({"type": "", "id": "", "file": "/missing"}), "")

    def test_new_selection_never_receives_old_plot(self):
        old = {"file": "/old", "type": "episode", "id": "1", "label": "Old", "plot": ""}
        new = {"file": "/new", "type": "episode", "id": "2", "label": "New", "plot": ""}
        props = {}
        home = Mock(getProperty=lambda k: props.get(k, ""),
                    setProperty=lambda k, v: props.__setitem__(k, v),
                    clearProperty=lambda k: props.pop(k, None))
        monitor = Mock(abortRequested=Mock(side_effect=[False, True]),
                       waitForAbort=Mock(return_value=False))
        with patch.object(plotter.xbmcgui, "Window", create=True, return_value=home), \
                patch.object(plotter.xbmc, "Monitor", create=True, return_value=monitor), \
                patch.object(plotter.xbmc, "getCondVisibility", create=True, return_value=True), \
                patch.object(plotter, "selected_item", side_effect=[old, old, new]), \
                patch.object(plotter, "lookup_plot", return_value="Old synopsis"):
            plotter.run()
        self.assertNotEqual(props.get("MyMetropolis.QueuePlot"), "Old synopsis")

    def test_plot_is_published_and_helper_cleans_up(self):
        selected = {"file": "/episode", "type": "episode", "id": "1", "label": "Episode", "plot": ""}
        props = {}
        home = Mock(getProperty=lambda k: props.get(k, ""),
                    setProperty=lambda k, v: props.__setitem__(k, v),
                    clearProperty=lambda k: props.pop(k, None))
        monitor = Mock(abortRequested=Mock(side_effect=[False, True]),
                       waitForAbort=Mock(return_value=False))
        with patch.object(plotter.xbmcgui, "Window", create=True, return_value=home), \
                patch.object(plotter.xbmc, "Monitor", create=True, return_value=monitor), \
                patch.object(plotter.xbmc, "getCondVisibility", create=True, return_value=True), \
                patch.object(plotter, "selected_item", return_value=selected), \
                patch.object(plotter, "lookup_plot", return_value="Library synopsis"):
            plotter.run()
        self.assertEqual(props["MyMetropolis.QueuePlot"], "Library synopsis")
        self.assertNotIn("MyMetropolis.PlotSession", props)


if __name__ == "__main__":
    unittest.main()
