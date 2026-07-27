"""Exercises the real Argon2id primitive directly (kept out of the service tests
so those stay fast with a fake hasher)."""

import unittest

from services.application.app.auth.password import Argon2PasswordHasher


class Argon2PasswordHasherTest(unittest.TestCase):
    def setUp(self) -> None:
        self.hasher = Argon2PasswordHasher()

    def test_hash_is_not_plaintext_and_is_argon2id(self) -> None:
        digest = self.hasher.hash("s3cret-pw")
        self.assertNotIn("s3cret-pw", digest)
        # Locks the variant: a library default flip to argon2i/d would fail here.
        self.assertTrue(digest.startswith("$argon2id$"))

    def test_verify_two_directional(self) -> None:
        digest = self.hasher.hash("s3cret-pw")
        # under-strict: if hashing/verify silently broke, the correct password
        # would stop verifying and this fails.
        self.assertTrue(self.hasher.verify(digest, "s3cret-pw"))
        # over-strict: if verify degenerated to "always true", a wrong password
        # would be accepted and this fails.
        self.assertFalse(self.hasher.verify(digest, "wrong-pw"))

    def test_same_password_hashes_differ_salted(self) -> None:
        self.assertNotEqual(self.hasher.hash("pw"), self.hasher.hash("pw"))

    def test_malformed_stored_hash_is_nonmatch_not_error(self) -> None:
        self.assertFalse(self.hasher.verify("not-a-real-hash", "pw"))


if __name__ == "__main__":
    unittest.main()
