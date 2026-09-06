"""Tests for deterministic generated-HTML evaluation."""

import unittest

from utils.deterministic_evaluator import evaluate_html


VALID_HTML = """<!DOCTYPE html>
<html lang="en"><head><title>Developer Portfolio</title>
<meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body><header><nav>Navigation</nav></header><main>
<h1>Developer Portfolio</h1><section id="about"><h2>About</h2><p>About the developer.</p></section>
<section id="projects"><h2>Projects</h2><img src="profile.png" alt="Developer portrait"></section>
<section id="contact"><h2>Contact</h2><label for="email">Email</label><input id="email" type="email"><button>Send message</button></section>
</main><footer>Copyright</footer><script>const status = { ready: true };</script></body></html>"""


class DeterministicEvaluatorTests(unittest.TestCase):
    def test_complete_document_scores_highly(self):
        report = evaluate_html(
            VALID_HTML,
            title="Developer portfolio",
            description="Portfolio with about, projects, and contact sections",
            check_external_resources=False,
        )

        self.assertGreater(report["score"], 9.0)
        self.assertEqual(report["issues"], [])

    def test_missing_accessibility_and_structure_are_reported(self):
        report = evaluate_html(
            "<html><body><h1>One</h1><h1>Two</h1><h3>Skipped</h3><img src='x.png'></body></html>",
            check_external_resources=False,
        )

        self.assertLess(report["score"], 6.0)
        self.assertTrue(any("exactly one h1" in issue for issue in report["issues"]))
        self.assertTrue(any("Missing alt" in issue for issue in report["issues"]))

    def test_requested_sections_are_checked_against_user_brief(self):
        report = evaluate_html(
            VALID_HTML,
            description="Include a pricing section and a portfolio",
            check_external_resources=False,
        )

        self.assertIn("pricing", report["required_sections"])
        self.assertTrue(any("pricing" in issue for issue in report["issues"]))


if __name__ == "__main__":
    unittest.main()
