# -*- coding: utf-8 -*-
"""API identity: JWT wins; guest-* only without token."""

from __future__ import annotations

import unittest
from unittest import mock

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.deps import (
    ensure_guest_user,
    is_guest_id,
    resolve_request_user,
)


class ResolveRequestUserTests(unittest.TestCase):
    def test_guest_client_id_accepted_without_token(self) -> None:
        uid = resolve_request_user(
            client_user_id="guest-deadbeef01",
            access_token=None,
        )
        self.assertEqual(uid, "guest-deadbeef01")

    def test_non_guest_without_token_forbidden(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            resolve_request_user(
                client_user_id="11111111-2222-3333-4444-555555555555",
                access_token=None,
            )
        self.assertEqual(ctx.exception.status_code, 403)

    def test_token_identity_wins(self) -> None:
        # Mismatch between client id and JWT → 403
        with self.assertRaises(HTTPException) as ctx:
            resolve_request_user(
                client_user_id="guest-ignored",
                access_token="access.jwt",
                jwt_user_id="auth-user-xyz",
            )
        self.assertEqual(ctx.exception.status_code, 403)

        uid = resolve_request_user(
            client_user_id=None,
            access_token="access.jwt",
            jwt_user_id="auth-user-xyz",
        )
        self.assertEqual(uid, "auth-user-xyz")

        uid = resolve_request_user(
            client_user_id="auth-user-xyz",
            access_token="access.jwt",
            jwt_user_id="auth-user-xyz",
        )
        self.assertEqual(uid, "auth-user-xyz")

    def test_victim_uuid_with_token_mismatch_forbidden(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            resolve_request_user(
                client_user_id="victim-uuid-0000",
                access_token="access.jwt",
                jwt_user_id="real-auth-user",
            )
        self.assertEqual(ctx.exception.status_code, 403)

    def test_invalid_token_unauthorized(self) -> None:
        with mock.patch("api.deps.user_id_from_access_token", return_value=None):
            with self.assertRaises(HTTPException) as ctx:
                resolve_request_user(
                    client_user_id=None,
                    access_token="bad.token",
                    jwt_user_id=None,
                )
        self.assertEqual(ctx.exception.status_code, 401)

    def test_ensure_guest_refuses_non_guest(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            ensure_guest_user("11111111-2222-3333-4444-555555555555")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertTrue(is_guest_id("guest-abc"))


class ApiIdentityHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        from api.main import app

        self.client = TestClient(app)

    def test_victim_uuid_no_token_forbidden(self) -> None:
        r = self.client.get(
            "/v1/me",
            headers={"X-User-Id": "11111111-2222-3333-4444-555555555555"},
        )
        self.assertEqual(r.status_code, 403)

    def test_guest_header_ok(self) -> None:
        r = self.client.get(
            "/v1/me",
            headers={"X-User-Id": "guest-testid0001"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["user_id"], "guest-testid0001")
        self.assertTrue(r.json()["user"]["guest"])

    def test_token_wins_over_spoofed_header(self) -> None:
        def fake_uid(at: str | None) -> str | None:
            return "auth-from-jwt" if at else None

        with mock.patch("api.deps.user_id_from_access_token", side_effect=fake_uid):
            with mock.patch("api.main.user_id_from_access_token", side_effect=fake_uid):
                r = self.client.get(
                    "/v1/me",
                    headers={
                        "X-User-Id": "victim-uuid",
                        "X-Access-Token": "good.token",
                        "X-Refresh-Token": "refresh.token",
                    },
                )
        self.assertEqual(r.status_code, 403)

        with mock.patch("api.deps.user_id_from_access_token", side_effect=fake_uid):
            with mock.patch("api.main.user_id_from_access_token", side_effect=fake_uid):
                r2 = self.client.get(
                    "/v1/me",
                    headers={
                        "X-Access-Token": "good.token",
                        "X-Refresh-Token": "refresh.token",
                    },
                )
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["user_id"], "auth-from-jwt")


if __name__ == "__main__":
    unittest.main()
