# -*- coding: iso8859-1 -*-
# 
# Copyright (C) 2004-2005 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Tim Moloney <t.moloney@verizon.net>


from trac.db_default import data as default_data
from trac.config import Configuration
from trac.env import Environment
from trac.scripts import admin
from trac.test import InMemoryDatabase
from trac.util import get_date_format_hint, NaivePopen

import os
import re
import sys
import time
import unittest
import shlex
import ConfigParser

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

STRIP_TRAILING_SPACE = re.compile(r'( +)$', re.MULTILINE)


def load_expected_results(file, pattern):
    """
    Reads the file, named file, which contains test results separated by
    the a regular expression, pattern.  The test results are returned as
    a dictionary.
    """

    expected = {}
    compiled_pattern = re.compile(pattern)
    f = open(file, 'r')
    for line in f:
        line = line.rstrip()
        match = compiled_pattern.search(line)
        if match:
            test = match.groups()[0]
            expected[test] = ''
        else:
            expected[test] += line + '\n'
    f.close()
    return expected


"""
A subclass of Environment that keeps its' DB in memory.
"""
class InMemoryEnvironment(Environment):

    def get_db_cnx(self):
        if not hasattr(self, '_db'):
            self._db = InMemoryDatabase()
        return self._db

    def create(self, db_str=None):
        self.load_config()

    def verify(self):
        return True

    def setup_log(self):
        from trac.log import logger_factory
        self.log = logger_factory('null')

    def is_component_enabled(self, cls):
        return cls.__module__.startswith('trac.') and \
               cls.__module__.find('.tests.') == -1

    def load_config(self):
        self.config = Configuration(None)

    def save_config(self):
        pass


class SkipTest(Exception):
    pass


class TracadminTestCase(unittest.TestCase):
    """
    Tests the output of trac-admin and is meant to be used with
    .../trac/tests.py.
    """

    expected_results = load_expected_results(os.path.join(os.path.split(__file__)[0],
                                            'admin-tests.txt'),
                                            '===== (test_[^ ]+) =====')

    def setUp(self):
        self.env = InMemoryEnvironment('', create=True)
        self.db = self.env.get_db_cnx()

        self._admin = admin.TracAdmin()
        self._admin.env_set('', self.env)

        # Set test date to 11th Jan 2004
        self._test_date = time.strftime('%Y-%m-%d',
                                        (2004, 1, 11, 0, 0, 0, 6, 1, -1))

    def tearDown(self):
        self.env = None

    def _execute(self, cmd, strip_trailing_space=True):
        try:
            _err = sys.stderr
            _out = sys.stdout
            sys.stderr = sys.stdout = out = StringIO()
            try:
                self._admin.docmd(cmd)
            except SystemExit, e:
                pass
            if strip_trailing_space:
                return STRIP_TRAILING_SPACE.sub('', out.getvalue())
            else:
                return out.getvalue()
        finally:
            sys.stderr = _err
            sys.stdout = _out

    def _require_python(self, version):
        if sys.version_info < version:
            raise SkipTest, 'requires Python %d.%d.%d' % version

    # About test

    def test_about(self):
        """
        Tests the 'about' command in trac-admin.  Since the 'about' command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """

        from trac import __version__, __license_long__

        expected_results = """
Trac Admin Console %s
=================================================================
%s
""" % (__version__, __license_long__)
        test_results = self._execute('about', strip_trailing_space=False)
        self.assertEquals(expected_results, test_results)

    # Help test

    def test_help_ok(self):
        """
        Tests the 'help' command in trac-admin.  Since the 'help' command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """
        from trac import __version__

        test_name = sys._getframe().f_code.co_name
        d = {'version': __version__,
             'date_format_hint': get_date_format_hint()}
        expected_results = self.expected_results[test_name] % d
        test_results = self._execute('help')
        self.assertEquals(expected_results, test_results)

    # Permission tests

    def test_permission_list_ok(self):
        """
        Tests the 'permission list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """
        test_name = sys._getframe().f_code.co_name
        try:
            # textwrap not available in python < 2.3
            self._require_python((2, 3, 0))

            test_results = self._execute('permission list')
            self.assertEquals(self.expected_results[test_name], test_results)
        except SkipTest, e:
            print>>sys.stderr, 'Skipping test %s: %s' % (test_name, e)

    def test_permission_add_one_action_ok(self):
        """
        Tests the 'permission add' command in trac-admin.  This particular
        test passes valid arguments to add one permission and checks for
        success.
        """
        test_name = sys._getframe().f_code.co_name
        try:
            # textwrap not available in python < 2.3
            self._require_python((2, 3, 0))

            self._execute('permission add test_user WIKI_VIEW')
            test_results = self._execute('permission list')
            self.assertEquals(self.expected_results[test_name], test_results)
        except SkipTest, e:
            print>>sys.stderr, 'Skipping test %s: %s' % (test_name, e)

    def test_permission_add_multiple_actions_ok(self):
        """
        Tests the 'permission add' command in trac-admin.  This particular
        test passes valid arguments to add multiple permissions and checks for
        success.
        """
        test_name = sys._getframe().f_code.co_name
        try:
            # textwrap not available in python < 2.3
            self._require_python((2, 3, 0))

            self._execute('permission add test_user LOG_VIEW FILE_VIEW')
            test_results = self._execute('permission list')
            self.assertEquals(self.expected_results[test_name], test_results)
        except SkipTest, e:
            print>>sys.stderr, 'Skipping test %s: %s' % (test_name, e)

    def test_permission_remove_one_action_ok(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test passes valid arguments to remove one permission and checks for
        success.
        """
        test_name = sys._getframe().f_code.co_name
        try:
            # textwrap not available in python < 2.3
            self._require_python((2, 3, 0))

            self._execute('permission remove anonymous TICKET_MODIFY')
            test_results = self._execute('permission list')
            self.assertEquals(self.expected_results[test_name], test_results)
        except SkipTest, e:
            print>>sys.stderr, 'Skipping test %s: %s' % (test_name, e)

    def test_permission_remove_multiple_actions_ok(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test passes valid arguments to remove multiple permission and checks
        for success.
        """
        test_name = sys._getframe().f_code.co_name
        try:
            # textwrap not available in python < 2.3
            self._require_python((2, 3, 0))

            test_name = sys._getframe().f_code.co_name
            self._execute('permission remove anonymous WIKI_CREATE WIKI_MODIFY')
            test_results = self._execute('permission list')
            self.assertEquals(self.expected_results[test_name], test_results)
        except SkipTest, e:
            print>>sys.stderr, 'Skipping test %s: %s' % (test_name, e)

    # Component tests

    def test_component_list_ok(self):
        """
        Tests the 'component list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('component list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_component_add_ok(self):
        """
        Tests the 'component add' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        test_name = sys._getframe().f_code.co_name
        self._execute('component add new_component new_user')
        test_results = self._execute('component list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_component_add_error_already_exists(self):
        """
        Tests the 'component add' command in trac-admin.  This particular
        test passes a component name that already exists and checks for an
        error message.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('component add component1 new_user')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_component_rename_ok(self):
        """
        Tests the 'component rename' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        test_name = sys._getframe().f_code.co_name
        self._execute('component rename component1 changed_name')
        test_results = self._execute('component list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_component_rename_error_bad_component(self):
        """
        Tests the 'component rename' command in trac-admin.  This particular
        test tries to rename a component that does not exist.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('component rename bad_component changed_name')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_component_rename_error_bad_new_name(self):
        """
        Tests the 'component rename' command in trac-admin.  This particular
        test tries to rename a component to a name that already exists.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('component rename component1 component2')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_component_chown_ok(self):
        """
        Tests the 'component chown' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        test_name = sys._getframe().f_code.co_name
        self._execute('component chown component2 changed_owner')
        test_results = self._execute('component list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_component_chown_error_bad_component(self):
        """
        Tests the 'component chown' command in trac-admin.  This particular
        test tries to change the owner of a component that does not
        exist.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('component chown bad_component changed_owner')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_component_remove_ok(self):
        """
        Tests the 'component remove' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        test_name = sys._getframe().f_code.co_name
        self._execute('component remove component1')
        test_results = self._execute('component list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_component_remove_error_bad_component(self):
        """
        Tests the 'component remove' command in trac-admin.  This particular
        test tries to remove a component that does not exist.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('component remove bad_component')
        self.assertEquals(self.expected_results[test_name], test_results)

    # Ticket-type tests

    def test_ticket_type_list_ok(self):
        """
        Tests the 'ticket_type list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('ticket_type list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_ticket_type_add_ok(self):
        """
        Tests the 'ticket_type add' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        test_name = sys._getframe().f_code.co_name
        self._execute('ticket_type add new_type')
        test_results = self._execute('ticket_type list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_ticket_type_add_error_already_exists(self):
        """
        Tests the 'ticket_type add' command in trac-admin.  This particular
        test passes a ticket type that already exists and checks for an error
        message.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('ticket_type add defect')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_ticket_type_change_ok(self):
        """
        Tests the 'ticket_type change' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        test_name = sys._getframe().f_code.co_name
        self._execute('ticket_type change defect bug')
        test_results = self._execute('ticket_type list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_ticket_type_change_error_bad_type(self):
        """
        Tests the 'ticket_type change' command in trac-admin.  This particular
        test tries to change a priority that does not exist.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('ticket_type change bad_type changed_type')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_ticket_type_change_error_bad_new_name(self):
        """
        Tests the 'ticket_type change' command in trac-admin.  This particular
        test tries to change a ticket type to another type that already exists.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('ticket_type change defect task')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_ticket_type_remove_ok(self):
        """
        Tests the 'ticket_type remove' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        test_name = sys._getframe().f_code.co_name
        self._execute('ticket_type remove task')
        test_results = self._execute('ticket_type list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_ticket_type_remove_error_bad_type(self):
        """
        Tests the 'ticket_type remove' command in trac-admin.  This particular
        test tries to remove a ticket type that does not exist.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('ticket_type remove bad_type')
        self.assertEquals(self.expected_results[test_name], test_results)

    # Priority tests

    def test_priority_list_ok(self):
        """
        Tests the 'priority list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('priority list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_priority_add_ok(self):
        """
        Tests the 'priority add' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        test_name = sys._getframe().f_code.co_name
        self._execute('priority add new_priority')
        test_results = self._execute('priority list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_priority_add_error_already_exists(self):
        """
        Tests the 'priority add' command in trac-admin.  This particular
        test passes a priority name that already exists and checks for an
        error message.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('priority add blocker')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_priority_change_ok(self):
        """
        Tests the 'priority change' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        test_name = sys._getframe().f_code.co_name
        self._execute('priority change major normal')
        test_results = self._execute('priority list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_priority_change_error_bad_priority(self):
        """
        Tests the 'priority change' command in trac-admin.  This particular
        test tries to change a priority that does not exist.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('priority change bad_priority changed_name')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_priority_change_error_bad_new_name(self):
        """
        Tests the 'priority change' command in trac-admin.  This particular
        test tries to change a priority to a name that already exists.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('priority change major minor')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_priority_remove_ok(self):
        """
        Tests the 'priority remove' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        test_name = sys._getframe().f_code.co_name
        self._execute('priority remove major')
        test_results = self._execute('priority list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_priority_remove_error_bad_priority(self):
        """
        Tests the 'priority remove' command in trac-admin.  This particular
        test tries to remove a priority that does not exist.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('priority remove bad_priority')
        self.assertEquals(self.expected_results[test_name], test_results)

    # Severity tests

    def test_severity_list_ok(self):
        """
        Tests the 'severity list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('severity list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_severity_add_ok(self):
        """
        Tests the 'severity add' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        test_name = sys._getframe().f_code.co_name
        self._execute('severity add new_severity')
        test_results = self._execute('severity list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_severity_add_error_already_exists(self):
        """
        Tests the 'severity add' command in trac-admin.  This particular
        test passes a severity name that already exists and checks for an
        error message.
        """
        test_name = sys._getframe().f_code.co_name
        self._execute('severity add blocker')
        test_results = self._execute('severity add blocker')
        self.assertEquals(self.expected_results[test_name], test_results), test_results

    def test_severity_change_ok(self):
        """
        Tests the 'severity add' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        test_name = sys._getframe().f_code.co_name
        self._execute('severity add critical')
        self._execute('severity change critical "end-of-the-world"')
        test_results = self._execute('severity list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_severity_change_error_bad_severity(self):
        """
        Tests the 'severity change' command in trac-admin.  This particular
        test tries to change a severity that does not exist.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('severity change bad_severity changed_name')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_severity_change_error_bad_new_name(self):
        """
        Tests the 'severity change' command in trac-admin.  This particular
        test tries to change a severity to a name that already exists.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('severity add major')
        test_results = self._execute('severity add critical')
        test_results = self._execute('severity change critical major')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_severity_remove_ok(self):
        """
        Tests the 'severity add' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        test_name = sys._getframe().f_code.co_name
        self._execute('severity remove trivial')
        test_results = self._execute('severity list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_severity_remove_error_bad_severity(self):
        """
        Tests the 'severity remove' command in trac-admin.  This particular
        test tries to remove a severity that does not exist.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('severity remove bad_severity')
        self.assertEquals(self.expected_results[test_name], test_results)

    # Version tests

    def test_version_list_ok(self):
        """
        Tests the 'version list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('version list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_version_add_ok(self):
        """
        Tests the 'version add' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        test_name = sys._getframe().f_code.co_name
        self._execute('version add 9.9 "%s"' % self._test_date)
        test_results = self._execute('version list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_version_add_error_already_exists(self):
        """
        Tests the 'version add' command in trac-admin.  This particular
        test passes a version name that already exists and checks for an
        error message.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('version add 1.0 "%s"' % self._test_date)
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_version_rename_ok(self):
        """
        Tests the 'version rename' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        test_name = sys._getframe().f_code.co_name
        self._execute('version rename 1.0 9.9')
        test_results = self._execute('version list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_version_rename_error_bad_version(self):
        """
        Tests the 'version rename' command in trac-admin.  This particular
        test tries to rename a version that does not exist.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('version rename bad_version changed_name')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_version_time_ok(self):
        """
        Tests the 'version time' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        test_name = sys._getframe().f_code.co_name
        self._execute('version time 2.0 "%s"' % self._test_date)
        test_results = self._execute('version list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_version_time_error_bad_version(self):
        """
        Tests the 'version time' command in trac-admin.  This particular
        test tries to change the time on a version that does not exist.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('version time bad_version "%s"' % self._test_date)
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_version_remove_ok(self):
        """
        Tests the 'version remove' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        test_name = sys._getframe().f_code.co_name
        self._execute('version remove 1.0')
        test_results = self._execute('version list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_version_remove_error_bad_version(self):
        """
        Tests the 'version remove' command in trac-admin.  This particular
        test tries to remove a version that does not exist.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('version remove bad_version')
        self.assertEquals(self.expected_results[test_name], test_results)

    # Milestone tests

    def test_milestone_list_ok(self):
        """
        Tests the 'milestone list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('milestone list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_milestone_add_ok(self):
        """
        Tests the 'milestone add' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        test_name = sys._getframe().f_code.co_name
        self._execute('milestone add new_milestone "%s"' % self._test_date)
        test_results = self._execute('milestone list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_milestone_add_error_already_exists(self):
        """
        Tests the 'milestone add' command in trac-admin.  This particular
        test passes a milestone name that already exists and checks for an
        error message.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('milestone add milestone1 "%s"' % self._test_date)
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_milestone_rename_ok(self):
        """
        Tests the 'milestone rename' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        test_name = sys._getframe().f_code.co_name
        self._execute('milestone rename milestone1 changed_milestone')
        test_results = self._execute('milestone list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_milestone_rename_error_bad_milestone(self):
        """
        Tests the 'milestone rename' command in trac-admin.  This particular
        test tries to rename a milestone that does not exist.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('milestone rename bad_milestone changed_name')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_milestone_due_ok(self):
        """
        Tests the 'milestone due' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        test_name = sys._getframe().f_code.co_name
        self._execute('milestone due milestone2 "%s"' % self._test_date)
        test_results = self._execute('milestone list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_milestone_due_error_bad_milestone(self):
        """
        Tests the 'milestone due' command in trac-admin.  This particular
        test tries to change the due date on a milestone that does not exist.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('milestone due bad_milestone "%s"' % self._test_date)
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_milestone_completed_ok(self):
        """
        Tests the 'milestone completed' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        test_name = sys._getframe().f_code.co_name

        self._execute('milestone completed milestone2 "%s"' % self._test_date)
        test_results = self._execute('milestone list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_milestone_completed_error_bad_milestone(self):
        """
        Tests the 'milestone completed' command in trac-admin.  This particular
        test tries to change the completed date on a milestone that does not
        exist.
        """
        test_name = sys._getframe().f_code.co_name

        test_results = self._execute('milestone completed bad_milestone "%s"' % self._test_date)
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_milestone_remove_ok(self):
        """
        Tests the 'milestone remove' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        test_name = sys._getframe().f_code.co_name
        self._execute('milestone remove milestone3')
        test_results = self._execute('milestone list')
        self.assertEquals(self.expected_results[test_name], test_results)

    def test_milestone_remove_error_bad_milestone(self):
        """
        Tests the 'milestone remove' command in trac-admin.  This particular
        test tries to remove a milestone that does not exist.
        """
        test_name = sys._getframe().f_code.co_name
        test_results = self._execute('milestone remove bad_milestone')
        self.assertEquals(self.expected_results[test_name], test_results)


def suite():
    return unittest.makeSuite(TracadminTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
