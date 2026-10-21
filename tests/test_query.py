import json
import unittest
from pathlib import Path

from wox_plugin import Context

from src.powertoys_main import _ACTIONS, _PINYIN_INDEX, PowerToysPlugin, _match_actions

_REPO_ROOT = Path(__file__).resolve().parents[1]
with (_REPO_ROOT / "plugin.json").open(encoding="utf-8") as _plugin_json:
    _I18N: dict[str, dict[str, str]] = json.load(_plugin_json)["I18n"]
_ZH_TITLES: dict[str, str] = _I18N["zh_CN"]
_EN_TITLES: dict[str, str] = _I18N["en_US"]

_TITLES = {action.title_key: _ZH_TITLES[action.title_key] for action in _ACTIONS}


def _matched_keys(search: str) -> list[str]:
    return [action.title_key for action, _score in _match_actions(_ACTIONS, search, _TITLES)]


class TestQueryMatching(unittest.TestCase):
    def test_empty_search_keeps_declaration_order(self):
        matches = _match_actions(_ACTIONS, "", _TITLES)
        self.assertEqual([action.title_key for action, _score in matches], [action.title_key for action in _ACTIONS])
        self.assertTrue(all(score > 0 for _action, score in matches))

    def test_english_keyword(self):
        self.assertEqual(_matched_keys("color"), ["color_picker"])

    def test_pinyin_initials(self):
        keys = _matched_keys("ys")
        self.assertEqual(keys[0], "color_picker")
        self.assertIn("color_picker", keys)

    def test_full_pinyin(self):
        self.assertEqual(_matched_keys("yanse"), ["color_picker"])

    def test_chinese_title_substring(self):
        self.assertEqual(_matched_keys("颜色"), ["color_picker"])

    def test_pinyin_works_with_english_ui_titles(self):
        keys = [action.title_key for action, _score in _match_actions(_ACTIONS, "yanse", _EN_TITLES)]
        self.assertEqual(keys, ["color_picker"])

    def test_pinyin_within_a_title(self):
        self.assertEqual(_matched_keys("ysxqq"), ["color_picker"])
        self.assertEqual(_matched_keys("xianshiyanse"), ["color_picker"])

    def test_exact_pinyin_match_ranks_above_prefix_match(self):
        keys = _matched_keys("qiehuan")
        self.assertEqual(keys[0], "toggle_easy_mouse")
        self.assertIn("light_switch_toggle", keys)
        self.assertIn("power_display_toggle", keys)

    def test_multi_term_query_requires_every_term(self):
        self.assertEqual(_matched_keys("always opacity"), ["always_on_top_increase_opacity", "always_on_top_decrease_opacity"])
        self.assertEqual(_matched_keys("窗口 截图"), ["crop_and_lock_screenshot"])

    def test_no_match_returns_empty(self):
        self.assertEqual(_matched_keys("zzzzzz"), [])

    def test_pinyin_index_covers_every_chinese_title(self):
        title_keys = {action.title_key for action in _ACTIONS}
        self.assertLessEqual(set(_PINYIN_INDEX), title_keys)
        for action in _ACTIONS:
            title = _ZH_TITLES[action.title_key]
            has_han = any("\u4e00" <= char <= "\u9fff" for char in title)
            if has_han:
                self.assertTrue(_PINYIN_INDEX.get(action.title_key), action.title_key)

    def test_scores_are_integers(self):
        for search in ("", "ys", "qiehuan", "always opacity", "窗口 截图"):
            for _action, score in _match_actions(_ACTIONS, search, _TITLES):
                self.assertIsInstance(score, int)
                self.assertNotIn(".", json.dumps(score))


class TestResultSerialization(unittest.IsolatedAsyncioTestCase):
    async def test_make_result_uses_integer_score_and_group_score(self):
        plugin = PowerToysPlugin()
        plugin._translations["keywords"] = "Keywords"

        result = await plugin._make_result(Context.new(), _ACTIONS[0], 138)
        data = json.loads(result.to_json())

        self.assertEqual(data["Score"], 138)
        self.assertEqual(data["GroupScore"], 0)
        self.assertIsInstance(data["Score"], int)
        self.assertIsInstance(data["GroupScore"], int)


if __name__ == "__main__":
    unittest.main()
