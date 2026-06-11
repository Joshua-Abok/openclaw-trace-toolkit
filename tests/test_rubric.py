import unittest

import rubric


def make_rubric():
    return {"dimensions": {
        "task_completion": {"weight": 0.5, "description": "done?"},
        "safety_privacy": {"weight": 0.5, "description": "safe?"},
    }}


class RubricTests(unittest.TestCase):
    def test_perfect_score_is_one(self):
        total = rubric.score(make_rubric(), {"task_completion": 5, "safety_privacy": 5})
        self.assertAlmostEqual(total, 1.0)

    def test_weighted_average(self):
        total = rubric.score(make_rubric(), {"task_completion": 5, "safety_privacy": 0})
        self.assertAlmostEqual(total, 0.5)

    def test_missing_dimension_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing scores"):
            rubric.score(make_rubric(), {"task_completion": 5})

    def test_unknown_dimension_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown dimensions"):
            rubric.score(make_rubric(),
                         {"task_completion": 5, "safety_privacy": 5, "vibes": 5})

    def test_out_of_range_score_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside 0-5"):
            rubric.score(make_rubric(), {"task_completion": 6, "safety_privacy": 5})

    def test_blank_sheet_covers_all_dimensions(self):
        sheet = rubric.blank_sheet(make_rubric())
        self.assertEqual(set(sheet["scores"]), {"task_completion", "safety_privacy"})
        self.assertTrue(all(v is None for v in sheet["scores"].values()))


if __name__ == "__main__":
    unittest.main()
