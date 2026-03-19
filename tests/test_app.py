import unittest
from uuid import uuid4

from werkzeug.security import generate_password_hash

from app import app, db, Admin, Driver, RideRequest, User
from graph_with_coords import coordinates


class EVTSTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with app.app_context():
            db.create_all()
            if not Admin.query.filter_by(email='admin@gmail.com').first():
                db.session.add(
                    Admin(
                        email='admin@gmail.com',
                        name='System Administrator',
                        password=generate_password_hash('Admin123'),
                    )
                )
                db.session.commit()

    def setUp(self):
        self.client = app.test_client()
        self.user_email = f"test-user-{uuid4().hex[:8]}@example.com"
        self.driver_email = f"test-driver-{uuid4().hex[:8]}@example.com"
        self.node = next(iter(coordinates))

        with app.app_context():
            db.session.add(
                User(
                    email=self.user_email,
                    name='Test User',
                    phone='9800000001',
                    password=generate_password_hash('Password123'),
                    latitude=27.7172,
                    longitude=85.3240,
                )
            )
            db.session.add(
                Driver(
                    email=self.driver_email,
                    name='Test Driver',
                    phone='9811111112',
                    password=generate_password_hash('Password123'),
                    vehicle='Ambulance',
                    node=self.node,
                    is_approved=True,
                )
            )
            db.session.commit()

    def tearDown(self):
        with app.app_context():
            RideRequest.query.filter(
                RideRequest.user_email.in_([self.user_email, 'deleted_user@gmail.com'])
                | RideRequest.driver_email.in_([self.driver_email, 'deleted_driver@gmail.com'])
            ).delete(synchronize_session=False)
            Driver.query.filter_by(email=self.driver_email).delete()
            User.query.filter_by(email=self.user_email).delete()
            db.session.commit()

    def login_session(self, role, email):
        with self.client.session_transaction() as sess:
            sess.clear()
            sess[role] = email

    def test_login_page_loads(self):
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 200)

    def test_login_redirects_user_without_role_selection(self):
        response = self.client.post(
            '/login',
            data={'username': self.user_email, 'password': 'Password123'},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get('Location'), '/user-home')

    def test_login_redirects_driver_without_role_selection(self):
        response = self.client.post(
            '/login',
            data={'username': self.driver_email, 'password': 'Password123'},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get('Location'), '/driver-home')

    def test_login_redirects_admin_without_role_selection(self):
        response = self.client.post(
            '/login',
            data={'username': 'admin@gmail.com', 'password': 'Admin123'},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get('Location'), '/admin/dashboard')

    def test_user_profile_page_loads(self):
        self.login_session('user', self.user_email)
        response = self.client.get('/edit-user-profile')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Edit Your Profile', response.data)

    def test_driver_profile_page_loads(self):
        self.login_session('driver', self.driver_email)
        response = self.client.get('/edit-driver-profile')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Edit Driver Profile', response.data)

    def test_request_accept_and_complete_ride_flow(self):
        self.login_session('user', self.user_email)
        request_response = self.client.post(
            '/request-ride',
            json={'driver_email': self.driver_email},
        )
        self.assertEqual(request_response.status_code, 200)
        self.assertTrue(request_response.get_json()['success'])

        with app.app_context():
            ride = RideRequest.query.filter_by(
                user_email=self.user_email, driver_email=self.driver_email
            ).order_by(RideRequest.id.desc()).first()
            self.assertIsNotNone(ride)
            ride_id = ride.id

        self.login_session('driver', self.driver_email)
        accept_response = self.client.post('/accept-request', json={'id': ride_id})
        self.assertEqual(accept_response.status_code, 200)
        self.assertTrue(accept_response.get_json()['success'])

        complete_response = self.client.post('/complete-ride', json={'ride_id': ride_id})
        self.assertEqual(complete_response.status_code, 200)
        self.assertTrue(complete_response.get_json()['success'])

        with app.app_context():
            completed_ride = db.session.get(RideRequest, ride_id)
            self.assertEqual(completed_ride.status, 'completed')

    def test_admin_can_delete_user(self):
        self.login_session('admin', 'admin@gmail.com')
        response = self.client.post(f'/admin/delete-user/{self.user_email}')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['success'])

        with app.app_context():
            self.assertIsNone(db.session.get(User, self.user_email))

    def test_admin_can_delete_driver(self):
        self.login_session('admin', 'admin@gmail.com')
        response = self.client.post(f'/admin/delete-driver/{self.driver_email}')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['success'])

        with app.app_context():
            self.assertIsNone(db.session.get(Driver, self.driver_email))


if __name__ == '__main__':
    unittest.main()
