"""Read-only endpoint load test. Credentials are supplied through environment settings.
Run only against an explicitly approved target; this script creates no seed data.
"""
import os
import random
import json
from pathlib import Path
from locust import HttpUser, task, between
from locust.exception import StopUser

class HostelAttendanceLoadTester(HttpUser):
    wait_time = between(1, 2.5)

    def on_start(self):
        self.token = None
        self.scenario = None
        scenario_file = os.getenv('LOAD_TEST_SCENARIOS_FILE')
        if scenario_file:
            scenarios = json.loads(Path(scenario_file).read_text(encoding='utf-8'))
            if not isinstance(scenarios, list) or not scenarios:
                raise StopUser('Scenario file must contain an array of accounts and read-only checks')
            self.scenario = random.choice(scenarios)
        username = self.scenario['username'] if self.scenario else os.getenv('LOAD_TEST_USERNAME')
        password = self.scenario['password'] if self.scenario else os.getenv('LOAD_TEST_PASSWORD')
        if not username or not password:
            raise StopUser('LOAD_TEST_USERNAME and LOAD_TEST_PASSWORD are required')
        with self.client.post('/api/auth/login', json={'username': username, 'password': password}, name='Login', catch_response=True) as response:
            if response.status_code != 200:
                response.failure('Authentication failed; virtual user stopped')
                raise StopUser()
            self.token = response.json().get('access_token')
            if not self.token:
                response.failure('Missing access token')
                raise StopUser()

    @task(4)
    def verify_expected_attendance(self):
        """Compare known test-fixture results under traffic; never creates fixtures.

        Scenario checks: {path, status:200, expected:{currently_in:2}}.
        List checks can supply expected_ids and id_field (e.g. StudentId).
        Fixtures must be stable during a correctness run.
        """
        if not self.scenario:
            return
        for check in self.scenario.get('checks', []):
            path = check['path']
            if not path.startswith('/api/') or path.startswith('//'):
                raise StopUser('Checks must use local API paths')
            with self.client.get(path, headers={'Authorization': f'Bearer {self.token}'},
                                 name='Attendance correctness / role scope', catch_response=True) as response:
                if response.status_code != check.get('status', 200):
                    response.failure('Expected role permission or HTTP status does not match')
                    continue
                if response.status_code != 200:
                    continue
                try:
                    data = response.json()
                    expected = check.get('expected', {})
                    if expected and (not isinstance(data, dict) or any(data.get(key) != value for key, value in expected.items())):
                        response.failure('Attendance state differs from the fixture')
                    if 'expected_ids' in check:
                        actual = [row[check['id_field']] for row in data]
                        if sorted(actual) != sorted(check['expected_ids']):
                            response.failure('Returned records differ from expected role scope / page')
                except (ValueError, KeyError, TypeError):
                    response.failure('Invalid correctness response')

    def read(self, path, expected, name=None):
        with self.client.get(path, headers={'Authorization': f'Bearer {self.token}'}, name=name or path, catch_response=True) as response:
            if response.status_code in (401, 403):
                response.failure('Session expired or account is not authorized')
                raise StopUser()
            if response.status_code != 200:
                response.failure(f'Unexpected HTTP status {response.status_code}')
                return
            try:
                data = response.json()
                if not expected(data):
                    response.failure('Response does not meet expected contract')
            except ValueError:
                response.failure('Invalid JSON response')

    @task(6)
    def dashboard(self):
        self.read('/api/dashboard/summary', lambda data: all(k in data for k in ['total_students','currently_in','currently_out']))

    @task(5)
    def attendance(self):
        self.read('/api/attendance/today?limit=100', lambda data: isinstance(data, list))

    @task(4)
    def students(self):
        query = random.choice(['8001','Rahul','Singh',''])
        self.read(f'/api/students?search={query}&limit=50', lambda data: isinstance(data,list), 'Student search')

    @task(3)
    def history(self):
        self.read('/api/attendance/history?limit=100', lambda data: isinstance(data,list))

    @task(2)
    def hostels(self):
        self.read('/api/hostels', lambda data: isinstance(data,list))

    @task(1)
    def ping(self):
        self.read('/api/system/ping', lambda data: data.get('status') == 'UP')
