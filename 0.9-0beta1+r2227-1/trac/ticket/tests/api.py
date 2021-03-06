from trac.config import Configuration
from trac.ticket.api import TicketSystem
from trac.test import EnvironmentStub, Mock

import unittest


class TicketSystemTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.ticket_system = TicketSystem(self.env)

    def test_custom_field_text(self):
        self.env.config.set('ticket-custom', 'test', 'text')
        self.env.config.set('ticket-custom', 'test.label', 'Test')
        self.env.config.set('ticket-custom', 'test.value', 'Foo bar')
        fields = TicketSystem(self.env).get_custom_fields()
        self.assertEqual({'name': 'test', 'type': 'text', 'label': 'Test',
                          'value': 'Foo bar', 'order': 0},
                         fields[0])

    def test_custom_field_select(self):
        self.env.config.set('ticket-custom', 'test', 'select')
        self.env.config.set('ticket-custom', 'test.label', 'Test')
        self.env.config.set('ticket-custom', 'test.value', '1')
        self.env.config.set('ticket-custom', 'test.options', 'option1|option2')
        fields = TicketSystem(self.env).get_custom_fields()
        self.assertEqual({'name': 'test', 'type': 'select', 'label': 'Test',
                          'value': '1', 'options': ['option1', 'option2'],
                          'order': 0},
                         fields[0])

    def test_custom_field_textarea(self):
        self.env.config.set('ticket-custom', 'test', 'textarea')
        self.env.config.set('ticket-custom', 'test.label', 'Test')
        self.env.config.set('ticket-custom', 'test.value', 'Foo bar')
        self.env.config.set('ticket-custom', 'test.cols', '60')
        self.env.config.set('ticket-custom', 'test.rows', '4')
        fields = TicketSystem(self.env).get_custom_fields()
        self.assertEqual({'name': 'test', 'type': 'textarea', 'label': 'Test',
                          'value': 'Foo bar', 'width': '60', 'height': '4',
                          'order': 0},
                         fields[0])

    def test_custom_field_order(self):
        self.env.config.set('ticket-custom', 'test1', 'text')
        self.env.config.set('ticket-custom', 'test1.order', '2')
        self.env.config.set('ticket-custom', 'test2', 'text')
        self.env.config.set('ticket-custom', 'test2.order', '1')
        fields = TicketSystem(self.env).get_custom_fields()
        self.assertEqual('test2', fields[0]['name'])
        self.assertEqual('test1', fields[1]['name'])

    def test_available_actions_full_perms(self):
        ts = TicketSystem(self.env)
        perm = Mock(has_permission=lambda x: 1)
        self.assertEqual(['leave', 'resolve', 'reassign', 'accept'],
                         ts.get_available_actions({'status': 'new'}, perm))
        self.assertEqual(['leave', 'resolve', 'reassign'],
                         ts.get_available_actions({'status': 'assigned'}, perm))
        self.assertEqual(['leave', 'resolve', 'reassign'],
                         ts.get_available_actions({'status': 'reopened'}, perm))
        self.assertEqual(['leave', 'reopen'],
                         ts.get_available_actions({'status': 'closed'}, perm))

    def test_available_actions_no_perms(self):
        ts = TicketSystem(self.env)
        perm = Mock(has_permission=lambda x: 0)
        self.assertEqual(['leave'],
                         ts.get_available_actions({'status': 'new'}, perm))
        self.assertEqual(['leave'],
                         ts.get_available_actions({'status': 'assigned'}, perm))
        self.assertEqual(['leave'],
                         ts.get_available_actions({'status': 'reopened'}, perm))
        self.assertEqual(['leave'],
                         ts.get_available_actions({'status': 'closed'}, perm))

    def test_available_actions_create_only(self):
        ts = TicketSystem(self.env)
        perm = Mock(has_permission=lambda x: x == 'TICKET_CREATE')
        self.assertEqual(['leave'],
                         ts.get_available_actions({'status': 'new'}, perm))
        self.assertEqual(['leave'],
                         ts.get_available_actions({'status': 'assigned'}, perm))
        self.assertEqual(['leave'],
                         ts.get_available_actions({'status': 'reopened'}, perm))
        self.assertEqual(['leave', 'reopen'],
                         ts.get_available_actions({'status': 'closed'}, perm))

    def test_available_actions_chgprop_only(self):
        ts = TicketSystem(self.env)
        perm = Mock(has_permission=lambda x: x == 'TICKET_CHGPROP')
        self.assertEqual(['leave', 'reassign', 'accept'],
                         ts.get_available_actions({'status': 'new'}, perm))
        self.assertEqual(['leave', 'reassign'],
                         ts.get_available_actions({'status': 'assigned'}, perm))
        self.assertEqual(['leave', 'reassign'],
                         ts.get_available_actions({'status': 'reopened'}, perm))
        self.assertEqual(['leave'],
                         ts.get_available_actions({'status': 'closed'}, perm))


def suite():
    return unittest.makeSuite(TicketSystemTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
