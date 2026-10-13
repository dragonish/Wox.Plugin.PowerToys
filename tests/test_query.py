import unittest

from src.powertoys_main import PowerToysPlugin


class TestMyPlugin(unittest.TestCase):
    def setUp(self):
        self.plugin = PowerToysPlugin()

    # def test_query(self):
    #     results = self.plugin.query(None, {"search": "test"})
    #     self.assertIsNotNone(results)


if __name__ == "__main__":
    unittest.main()
