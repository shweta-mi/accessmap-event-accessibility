import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

import main


class AccessMapWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "test.sqlite3"
        self.db_patch = patch.object(main, "DB_PATH", db_path)
        self.key_patch = patch.object(main, "ADMIN_KEY", "test-only-secret")
        self.db_patch.start()
        self.key_patch.start()
        main.initialize_database()

    def tearDown(self):
        self.key_patch.stop()
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_seed_records_are_explicitly_demo(self):
        result = main.places(step_free=False, restroom=False, area="", verification="all")
        self.assertEqual(len(result["places"]), 4)
        self.assertEqual(result["counts"], {"verified": 0, "demo": 4})
        self.assertTrue(all(place["verification_status"] == "demo" for place in result["places"]))

    def test_filters_combine(self):
        result = main.places(step_free=True, restroom=True, area="", verification="all")
        self.assertEqual([place["name"] for place in result["places"]], ["Civic Hall Demo Venue"])

    def test_suggestion_is_private_until_approved(self):
        suggestion = main.Suggestion(
            name="Library Event Room", area="Civil Lines", latitude=25.45, longitude=81.83,
            step_free=True, accessible_restroom=None, transit="Medium",
            evidence="On-site visit and venue staff confirmation", details="Entrance via side ramp.",
        )
        created = main.submit_suggestion(suggestion)
        self.assertEqual(created["status"], "pending")
        public = main.places(step_free=False, restroom=False, area="", verification="all")
        self.assertEqual(len(public["places"]), 4)
        pending = main.list_submissions(x_admin_key="test-only-secret")["submissions"]
        self.assertEqual(pending[0]["status"], "pending")

    def test_admin_key_is_required(self):
        with self.assertRaises(HTTPException) as raised:
            main.list_submissions(x_admin_key="wrong")
        self.assertEqual(raised.exception.status_code, 401)

    def test_approval_requires_source_and_date_and_adds_verified_record(self):
        suggestion = main.Suggestion(
            name="Community Library Room", area="George Town", latitude=25.44, longitude=81.84,
            step_free=True, accessible_restroom=True, transit="High",
            evidence="On-site visit with venue manager",
        )
        created = main.submit_suggestion(suggestion)
        with self.assertRaises(HTTPException) as raised:
            main.review_submission(created["id"], main.ReviewDecision(decision="approve"), "test-only-secret")
        self.assertEqual(raised.exception.status_code, 422)

        reviewed = main.review_submission(
            created["id"],
            main.ReviewDecision(
                decision="approve", verification_source="On-site visit with venue manager",
                verified_on=date(2026, 10, 22),
            ),
            "test-only-secret",
        )
        self.assertEqual(reviewed["status"], "approved")
        verified = main.places(step_free=True, restroom=True, area="", verification="verified")
        self.assertEqual(len(verified["places"]), 1)
        self.assertEqual(verified["places"][0]["verified_on"], "2026-10-22")
        self.assertEqual(verified["places"][0]["verification_source"], "On-site visit with venue manager")

    def test_rejected_suggestion_never_enters_public_directory(self):
        suggestion = main.Suggestion(
            name="Temporary Event Space", area="Naini", latitude=25.40, longitude=81.88,
            evidence="Community submitted listing, awaiting independent check",
        )
        created = main.submit_suggestion(suggestion)
        main.review_submission(created["id"], main.ReviewDecision(decision="reject"), "test-only-secret")
        public = main.places(step_free=False, restroom=False, area="", verification="all")
        self.assertEqual(len(public["places"]), 4)
        pending = main.list_submissions(x_admin_key="test-only-secret")["submissions"]
        self.assertEqual(pending[0]["status"], "rejected")

    def test_invalid_coordinates_are_rejected(self):
        with self.assertRaises(ValidationError):
            main.Suggestion(
                name="Bad Location Venue", area="Civil Lines", latitude=140, longitude=81,
                evidence="A sufficiently detailed source",
            )


if __name__ == "__main__":
    unittest.main()
