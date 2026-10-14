import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
for name in ("xbmc", "xbmcaddon", "xbmcgui", "xbmcvfs"):
    sys.modules[name] = types.ModuleType(name)
spec = importlib.util.spec_from_file_location("identify_episode",
                                             ROOT / "resources/identify_episode.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class IdentificationTests(unittest.TestCase):
    def setUp(self):
        self.dialog = Mock()
        helper.xbmcgui.Dialog = Mock(return_value=self.dialog)
        helper.xbmcgui.NOTIFICATION_INFO = "info"
        helper.xbmc.getCondVisibility = Mock(return_value=False)
        helper.xbmc.executebuiltin = Mock()
        helper.xbmcvfs.exists = Mock(return_value=True)
        self.original = {
            "episodeid": 12, "title": "Wrong title", "season": 1, "episode": 3,
            "file": "smb://media/TNG/Season 1/TNG S01E03.mkv", "tvshowid": 4,
            "playcount": 1, "resume": {"position": 22, "total": 2700}}
        self.candidate = {
            "id": 99, "name": "Correct title", "overview": "Correct plot",
            "season_number": 1, "episode_number": 4, "air_date": "1987-10-19",
            "still_path": "/correct.jpg", "vote_average": 7.2, "vote_count": 20,
            "credits": {"crew": [{"job": "Director", "name": "Director"}]}}
        self.api = Mock()
        self.api.get.side_effect = [
            {"id": 7, "name": "TNG", "seasons": [{"season_number": 1, "name": "Season 1"}]},
            {"episodes": [self.candidate]}, self.candidate]
        self.calls = []
        def rpc(method, **params):
            self.calls.append((method, params))
            if method == "VideoLibrary.GetEpisodeDetails":
                return {"episodedetails": dict(self.original)}
            if method == "VideoLibrary.GetTVShowDetails":
                return {"tvshowdetails": {"title": "TNG", "uniqueid": {"tmdb": "7"}}}
            return "OK"
        self.patches = [
            patch.object(helper, "rpc", side_effect=rpc),
            patch.object(helper, "read_json", return_value=None),
            patch.object(helper, "write_json"),
            patch.object(helper, "TMDb", return_value=self.api),
            patch.object(sys, "argv", ["identify_episode.py", "12"])]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.dialog.select.side_effect = [0, 1]
        self.dialog.yesno.return_value = True

    def updates(self):
        return [p for m, p in self.calls if m == "VideoLibrary.SetEpisodeDetails"]

    def test_corrects_episode_without_renaming_or_changing_playback(self):
        helper.main()
        params, = self.updates()
        self.assertEqual((params["title"], params["season"], params["episode"]),
                         ("Correct title", 1, 4))
        self.assertEqual(params["uniqueid"], {"tmdb": "99"})
        self.assertEqual(params["director"], ["Director"])
        self.assertTrue(params["art"]["thumb"].endswith("/correct.jpg"))
        self.assertTrue({"file", "playcount", "resume", "tvshowid"}.isdisjoint(params))
        helper.write_json.assert_called()
        self.assertEqual(helper.write_json.call_args_list[0].args[1]["file"],
                         self.original["file"])

    def test_cancel_season_is_read_only(self):
        self.dialog.select.side_effect = [-1]
        with self.assertRaises(helper.Cancelled):
            helper.main()
        self.assertFalse(self.updates())
        helper.write_json.assert_not_called()

    def test_reject_confirmation_is_read_only(self):
        self.dialog.yesno.return_value = False
        helper.main()
        self.assertFalse(self.updates())
        helper.write_json.assert_not_called()

    def test_backup_failure_blocks_update(self):
        helper.write_json.side_effect = RuntimeError("disk full")
        with self.assertRaises(RuntimeError):
            helper.main()
        self.assertFalse(self.updates())

    def test_undo_uses_saved_metadata_without_network(self):
        helper.read_json.return_value = {
            "file": self.original["file"],
            "before": {"episodeid": 12, "title": "Previous title", "season": 1, "episode": 2}}
        self.dialog.select.side_effect = [1]
        helper.main()
        self.assertEqual(self.updates()[0]["title"], "Previous title")
        helper.TMDb.assert_not_called()

    def test_database_id_reuse_cannot_modify_another_file(self):
        def rpc(method, **params):
            if method == "VideoLibrary.GetEpisodeDetails":
                item = dict(self.original)
                if self.api.get.call_count:
                    item["file"] = "smb://media/another.mkv"
                return {"episodedetails": item}
            return {"tvshowdetails": {"title": "TNG", "uniqueid": {"tmdb": "7"}}}
        helper.rpc.side_effect = rpc
        with self.assertRaisesRegex(RuntimeError, "library changed"):
            helper.main()
        helper.write_json.assert_not_called()

    def test_scan_blocks_identification(self):
        helper.xbmc.getCondVisibility.return_value = True
        with self.assertRaisesRegex(RuntimeError, "scan"):
            helper.main()
        helper.TMDb.assert_not_called()
        self.assertFalse(self.updates())

    def test_missing_art_clears_incorrect_thumbnail(self):
        self.candidate["still_path"] = None
        params = helper.episode_params(12, self.candidate)
        self.assertEqual(params["art"], {"thumb": ""})


if __name__ == "__main__":
    unittest.main()
