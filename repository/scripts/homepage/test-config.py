#!/usr/bin/env python3
"""Validate the real sanitized Homepage config, including proxy header nesting."""
import json
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlparse

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / 'stacks/admin/homepage'


class HomepageConfigTests(unittest.TestCase):
    def setUp(self):
        groups = yaml.safe_load((CONFIG / 'services.yaml').read_text())
        self.services = {
            name: service
            for group in groups for items in group.values()
            for item in items for name, service in item.items()
        }

    def test_schedule_proxy_headers_and_mappings_are_inside_widget(self):
        service = self.services['LoL Esports']
        self.assertNotIn('headers', service)
        widget = service['widget']
        self.assertEqual(widget['type'], 'customapi')
        self.assertEqual(widget['headers']['Content-Type'], 'application/json')
        self.assertEqual(widget['headers']['apollographql-client-name'], 'Esports Web')
        self.assertTrue(widget['headers']['apollographql-client-version'])
        self.assertEqual(widget['refreshInterval'], 300000)
        self.assertEqual(widget['mappings'][0]['field'], 'data.esports.events')

    def test_schedule_request_uses_official_upcoming_feed_without_expiring_date_bounds(self):
        url = urlparse(self.services['LoL Esports']['widget']['url'])
        self.assertEqual((url.scheme, url.netloc, url.path), ('https', 'lolesports.com', '/api/gql'))
        query = parse_qs(url.query)
        self.assertEqual(query['operationName'], ['homeEvents'])
        variables = json.loads(query['variables'][0])
        self.assertEqual(set(variables['eventState']), {'unstarted', 'inProgress'})
        self.assertEqual(variables['eventType'], 'match')
        self.assertEqual(variables['pageSize'], 40)
        self.assertEqual(len(set(variables['leagues'])), 9)
        self.assertNotIn('eventDateStart', variables)
        self.assertNotIn('eventDateEnd', variables)
        persisted = json.loads(query['extensions'][0])['persistedQuery']
        self.assertEqual(persisted['version'], 1)
        self.assertRegex(persisted['sha256Hash'], r'^[0-9a-f]{64}$')

    def test_current_services_and_private_credential_references(self):
        self.assertNotIn('XRDB', self.services)
        for name in ['PostersPlus', 'LumiereDB']:
            self.assertIn(name, self.services)
        variable = 'HOMEPAGE_VAR_AIOMETADATA_ADMIN_KEY'
        example = (ROOT / 'stacks/admin/.env.example').read_text()
        self.assertEqual(self.services['Image Cache']['widget']['headers']['x-admin-key'],
                         '{{' + variable + '}}')
        self.assertIn(variable + '=', example)

    def test_dashboard_opens_without_a_redundant_single_tab(self):
        settings = yaml.safe_load((CONFIG / 'settings.yaml').read_text())
        self.assertTrue(settings['layout'])
        self.assertFalse(any('tab' in layout for layout in settings['layout'].values()))


if __name__ == '__main__':
    unittest.main()
