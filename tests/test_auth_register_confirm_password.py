import unittest
from unittest.mock import MagicMock, patch

from flask import Flask

from app.controllers.auth_controller import auth_bp
from app.extensions import login_manager


class RegisterConfirmPasswordTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config["SECRET_KEY"] = "test-secret"
        self.app.config["TESTING"] = True
        login_manager.init_app(self.app)

        @login_manager.user_loader
        def _load_user(_user_id):
            return None

        self.app.register_blueprint(auth_bp)
        self.client = self.app.test_client()

    @patch("app.controllers.auth_controller.send_email")
    @patch("app.controllers.auth_controller.generate_verify_token", return_value="tok123")
    @patch("app.controllers.auth_controller.db")
    @patch("app.controllers.auth_controller.User")
    def test_register_accepts_legacy_confirm_password_key_when_matches(
        self, user_cls, db_mock, _token_mock, _email_mock
    ):
        user_query = MagicMock()
        user_query.first.return_value = None
        user_cls.query.filter_by.return_value = user_query

        response = self.client.post(
            "/auth/register",
            json={
                "email": "123@utpn.edu.mx",
                "password": "secreto123",
                "confirmPassword": "secreto123",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/?mode=login", response.location)
        db_mock.session.add.assert_called_once()
        db_mock.session.commit.assert_called_once()

    def test_register_returns_400_when_confirm_password_missing(self):
        response = self.client.post(
            "/auth/register",
            json={
                "email": "123@utpn.edu.mx",
                "password": "secreto123",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "confirm_password es obligatorio."})

    def test_register_returns_400_when_confirm_password_does_not_match(self):
        response = self.client.post(
            "/auth/register",
            json={
                "email": "123@utpn.edu.mx",
                "password": "secreto123",
                "confirm_password": "otra123",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Las contraseñas no coinciden."})


if __name__ == "__main__":
    unittest.main()
