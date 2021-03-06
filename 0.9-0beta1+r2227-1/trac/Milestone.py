# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2004-2005 Edgewall Software
# Copyright (C) 2004-2005 Christopher Lenz <cmlenz@gmx.de>
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
# Author: Christopher Lenz <cmlenz@gmx.de>

from __future__ import generators
import time

from trac.core import *
from trac.perm import IPermissionRequestor
from trac.ticket import Ticket, TicketSystem
from trac.Timeline import ITimelineEventProvider
from trac.util import *
from trac.web import IRequestHandler
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.wiki import wiki_to_html, wiki_to_oneliner, IWikiSyntaxProvider


class Milestone(object):

    def __init__(self, env, name=None, db=None):
        self.env = env
        if name:
            self._fetch(name, db)
            self._old_name = name
        else:
            self.name = self._old_name = None
            self.due = self.completed = 0
            self.description = ''

    def _fetch(self, name, db=None):
        if not db:
            db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT name,due,completed,description "
                       "FROM milestone WHERE name=%s", (name,))
        row = cursor.fetchone()
        if not row:
            raise TracError('Milestone %s does not exist.' % name,
                            'Invalid Milestone Name')
        self.name = row[0]
        self.due = row[1] and int(row[1]) or 0
        self.completed = row[2] and int(row[2]) or 0
        self.description = row[3] or ''

    exists = property(fget=lambda self: self._old_name is not None)
    is_completed = property(fget=lambda self: self.completed != 0)
    is_late = property(fget=lambda self: self.due and self.due < time.time())

    def delete(self, retarget_to=None, db=None):
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        cursor = db.cursor()
        self.env.log.info('Deleting milestone %s' % self.name)
        cursor.execute("DELETE FROM milestone WHERE name=%s", (self.name,))

        if retarget_to:
            self.env.log.info('Retargeting milestone field of all tickets '
                              'associated with milestone "%s" to milestone "%s"'
                              % (self.name, retarget_to))
            cursor.execute("UPDATE ticket SET milestone=%s WHERE milestone=%s",
                           (retarget_to, self.name))
        else:
            self.env.log.info('Resetting milestone field of all tickets '
                              'associated with milestone %s' % self.name)
            cursor.execute("UPDATE ticket SET milestone=NULL "
                           "WHERE milestone=%s", (self.name,))

        if handle_ta:
            db.commit()

    def insert(self, db=None):
        assert self.name, 'Cannot create milestone with no name'
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        cursor = db.cursor()
        self.env.log.debug("Creating new milestone '%s'" % self.name)
        cursor.execute("INSERT INTO milestone (name,due,completed,description) "
                       "VALUES (%s,%s,%s,%s)",
                       (self.name, self.due, self.completed, self.description))

        if handle_ta:
            db.commit()

    def update(self, db=None):
        assert self.name, 'Cannot update milestone with no name'
        if not db:
            db = self.env.get_db_cnx()
            handle_ta = True
        else:
            handle_ta = False

        cursor = db.cursor()
        self.env.log.info('Updating milestone "%s"' % self.name)
        cursor.execute("UPDATE milestone SET name=%s,due=%s,"
                       "completed=%s,description=%s WHERE name=%s",
                       (self.name, self.due, self.completed, self.description,
                        self._old_name))
        self.env.log.info('Updating milestone field of all tickets '
                          'associated with milestone "%s"' % self.name)
        cursor.execute("UPDATE ticket SET milestone=%s WHERE milestone=%s",
                       (self.name, self._old_name))
        # FIXME: Insert change into the change history of the tickets
        self._old_name = self.name

        if handle_ta:
            db.commit()

    def select(cls, env, include_completed=True, db=None):
        if not db:
            db = env.get_db_cnx()
        sql = "SELECT name,due,completed,description FROM milestone "
        if not include_completed:
            sql += "WHERE COALESCE(completed,0)=0 "
        sql += "ORDER BY COALESCE(due,0)=0,due,name"
        cursor = db.cursor()
        cursor.execute(sql)
        for name,due,completed,description in cursor:
            milestone = Milestone(env)
            milestone.name = milestone._old_name = name
            milestone.due = due and int(due) or 0
            milestone.completed = completed and int(completed) or 0
            milestone.description = description or ''
            yield milestone
    select = classmethod(select)


def get_tickets_for_milestone(env, db, milestone, field='component'):
    cursor = db.cursor()
    fields = TicketSystem(env).get_ticket_fields()
    if field in [f['name'] for f in fields if not f.get('custom')]:
        cursor.execute("SELECT id,status,%s FROM ticket WHERE milestone=%%s "
                       "ORDER BY %s" % (field, field), (milestone,))
    else:
        cursor.execute("SELECT id,status,value FROM ticket LEFT OUTER "
                       "JOIN ticket_custom ON (id=ticket AND name=%s) "
                       "WHERE milestone=%s ORDER BY value", (field, milestone))
    tickets = []
    for tkt_id, status, fieldval in cursor:
        tickets.append({'id': tkt_id, 'status': status, field: fieldval})
    return tickets

def get_query_links(env, milestone, grouped_by='component', group=None):
    q = {}
    if not group:
        q['all_tickets'] = env.href.query(milestone=milestone)
        q['active_tickets'] = env.href.query(milestone=milestone,
                                             status=('new', 'assigned', 'reopened'))
        q['closed_tickets'] = env.href.query(milestone=milestone, status='closed')
    else:
        q['all_tickets'] = env.href.query({grouped_by: group},
                                          milestone=milestone)
        q['active_tickets'] = env.href.query({grouped_by: group},
                                             milestone=milestone,
                                             status=('new', 'assigned', 'reopened'))
        q['closed_tickets'] = env.href.query({grouped_by: group},
                                             milestone=milestone,
                                             status='closed')
    return q

def calc_ticket_stats(tickets):
    total_cnt = len(tickets)
    active = [ticket for ticket in tickets if ticket['status'] != 'closed']
    active_cnt = len(active)
    closed_cnt = total_cnt - active_cnt

    percent_active, percent_closed = 0, 0
    if total_cnt > 0:
        percent_active = round(float(active_cnt) / float(total_cnt) * 100)
        percent_closed = round(float(closed_cnt) / float(total_cnt) * 100)
        if percent_active + percent_closed > 100:
            percent_closed -= 1

    return {
        'total_tickets': total_cnt,
        'active_tickets': active_cnt,
        'percent_active': percent_active,
        'closed_tickets': closed_cnt,
        'percent_closed': percent_closed
    }

def milestone_to_hdf(env, db, req, milestone):
    hdf = {'name': escape(milestone.name),
           'href': escape(env.href.milestone(milestone.name))}
    if milestone.description:
        hdf['description_source'] = escape(milestone.description)
        hdf['description'] = wiki_to_html(milestone.description, env, req, db)
    if milestone.due:
        hdf['due'] = milestone.due
        hdf['due_date'] = time.strftime('%x', time.localtime(milestone.due))
        hdf['due_delta'] = pretty_timedelta(milestone.due)
        hdf['late'] = milestone.is_late
    if milestone.completed:
        hdf['completed'] = milestone.completed
        hdf['completed_date'] = time.strftime('%x %X',
                                              time.localtime(milestone.completed))
        hdf['completed_delta'] = pretty_timedelta(milestone.completed)
    return hdf

def _get_groups(env, db, by='component'):
    for field in TicketSystem(env).get_ticket_fields():
        if field['name'] == by:
            if field.has_key('options'):
                return field['options']
            else:
                cursor = db.cursor()
                cursor.execute("SELECT DISTINCT %s FROM ticket ORDER BY %s"
                               % (by, by))
                return [row[0] for row in cursor]
    return []

def _parse_date(datestr):
    seconds = None
    datestr = datestr.strip()
    for format in ['%x %X', '%x, %X', '%X %x', '%X, %x', '%x', '%c',
                   '%b %d, %Y']:
        try:
            date = time.strptime(datestr, format)
            seconds = time.mktime(date)
            break
        except ValueError:
            continue
    if seconds == None:
        raise TracError('%s is not a known date format.' % datestr,
                        'Invalid Date Format')
    return seconds


class MilestoneModule(Component):

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler,
               ITimelineEventProvider, IWikiSyntaxProvider)

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'roadmap'

    def get_navigation_items(self, req):
        return []

    # IPermissionRequestor methods

    def get_permission_actions(self):
        actions = ['MILESTONE_CREATE', 'MILESTONE_DELETE', 'MILESTONE_MODIFY',
                   'MILESTONE_VIEW']
        return actions + [('ROADMAP_ADMIN', actions)]

    # ITimelineEventProvider methods

    def get_timeline_filters(self, req):
        if req.perm.has_permission('MILESTONE_VIEW'):
            yield ('milestone', 'Milestones')

    def get_timeline_events(self, req, start, stop, filters):
        if 'milestone' in filters:
            format = req.args.get('format')
            db = self.env.get_db_cnx()
            cursor = db.cursor()
            cursor.execute("SELECT completed,name,description FROM milestone "
                           "WHERE completed>=%s AND completed<=%s",
                           (start, stop,))
            for completed,name,description in cursor:
                title = 'Milestone <em>%s</em> completed' % escape(name)
                if format == 'rss':
                    href = self.env.abs_href.milestone(name)
                    message = wiki_to_html(description or '--', self.env, db,
                                           absurls=True)
                else:
                    href = self.env.href.milestone(name)
                    message = wiki_to_oneliner(shorten_line(description),
                                               self.env, db)
                yield 'milestone', href, title, completed, None, message

    # IRequestHandler methods

    def match_request(self, req):
        import re, urllib
        match = re.match(r'/milestone(?:/([^\?]+))?(?:/(.*)/?)?', req.path_info)
        if match:
            if match.group(1):
                req.args['id'] = urllib.unquote(match.group(1))
            return 1

    def process_request(self, req):
        req.perm.assert_permission('MILESTONE_VIEW')

        add_link(req, 'up', self.env.href.roadmap(), 'Roadmap')

        db = self.env.get_db_cnx()
        milestone = Milestone(self.env, req.args.get('id'), db)
        action = req.args.get('action', 'view')

        if req.method == 'POST':
            if req.args.has_key('cancel'):
                if milestone.exists:
                    req.redirect(self.env.href.milestone(milestone.name))
                else:
                    req.redirect(self.env.href.roadmap())
            elif action == 'edit':
                self._do_save(req, db, milestone)
            elif action == 'delete':
                self._do_delete(req, db, milestone)
        elif action in ('new', 'edit'):
            self._render_editor(req, db, milestone)
        elif action == 'delete':
            self._render_confirm(req, db, milestone)
        else:
            self._render_view(req, db, milestone)

        add_stylesheet(req, 'common/css/roadmap.css')
        return 'milestone.cs', None

    # Internal methods

    def _do_delete(self, req, db, milestone):
        req.perm.assert_permission('MILESTONE_DELETE')

        retarget_to = None
        if req.args.has_key('retarget'):
            retarget_to = req.args.get('target')
        milestone.delete(retarget_to)
        db.commit()
        req.redirect(self.env.href.roadmap())

    def _do_save(self, req, db, milestone):
        if milestone.exists:
            req.perm.assert_permission('MILESTONE_MODIFY')
        else:
            req.perm.assert_permission('MILESTONE_CREATE')

        if not req.args.has_key('name'):
            raise TracError('You must provide a name for the milestone.',
                            'Required Field Missing')
        milestone.name = req.args.get('name')

        due = req.args.get('duedate', '')
        milestone.due = due and _parse_date(due) or 0
        if req.args.has_key('completed'):
            completed = req.args.get('completeddate', '')
            milestone.completed = completed and _parse_date(completed) or 0
            if milestone.completed > time.time():
                raise TracError('Completion date may not be in the future',
                                'Invalid Completion Date')
        else:
            milestone.completed = 0

        milestone.description = req.args.get('description', '')

        if milestone.exists:
            milestone.update()
        else:
            milestone.insert()
        db.commit()
        req.redirect(self.env.href.milestone(milestone.name))

    def _render_confirm(self, req, db, milestone):
        req.perm.assert_permission('MILESTONE_DELETE')

        req.hdf['title'] = 'Milestone %s' % milestone.name
        req.hdf['milestone'] = milestone_to_hdf(self.env, db, req, milestone)
        req.hdf['milestone.mode'] = 'delete'

        for idx,other in enum(Milestone.select(self.env, False, db)):
            if other.name == milestone.name:
                continue
            req.hdf['milestones.%d' % idx] = other.name

    def _render_editor(self, req, db, milestone):
        if milestone.exists:
            req.perm.assert_permission('MILESTONE_MODIFY')
            req.hdf['title'] = 'Milestone %s' % milestone.name
            req.hdf['milestone.mode'] = 'edit'
        else:
            req.perm.assert_permission('MILESTONE_CREATE')
            req.hdf['title'] = 'New Milestone'
            req.hdf['milestone.mode'] = 'new'

        req.hdf['milestone'] = milestone_to_hdf(self.env, db, req, milestone)
        req.hdf['milestone.date_hint'] = get_date_format_hint()
        req.hdf['milestone.datetime_hint'] = get_datetime_format_hint()
        req.hdf['milestone.datetime_now'] = time.strftime('%x %X',
                                                          time.localtime(time.time()))

    def _render_view(self, req, db, milestone):
        req.hdf['title'] = 'Milestone %s' % milestone.name
        req.hdf['milestone.mode'] = 'view'

        # If the milestone name contains slashes, we'll need to include the 'id'
        # parameter in the forms for editing/deleting the milestone. See #806.
        if milestone.name.find('/') >= 0:
            req.hdf['milestone.id_param'] = 1

        req.hdf['milestone'] = milestone_to_hdf(self.env, db, req, milestone)

        available_groups = []
        component_group_available = False
        for field in TicketSystem(self.env).get_ticket_fields():
            if field['type'] == 'select' and field['name'] != 'milestone' \
                    or field['name'] == 'owner':
                available_groups.append({'name': field['name'],
                                         'label': field['label']})
                if field['name'] == 'component':
                    component_group_available = True
        req.hdf['milestone.stats.available_groups'] = available_groups

        if component_group_available:
            by = req.args.get('by', 'component')
        else:
            by = req.args.get('by', available_groups[0]['name'])
        req.hdf['milestone.stats.grouped_by'] = by

        tickets = get_tickets_for_milestone(self.env, db, milestone.name, by)
        stats = calc_ticket_stats(tickets)
        req.hdf['milestone.stats'] = stats
        for key, value in get_query_links(self.env, milestone.name).items():
            req.hdf['milestone.queries.' + key] = escape(value)

        groups = _get_groups(self.env, db, by)
        group_no = 0
        max_percent_total = 0
        for group in groups:
            group_tickets = [t for t in tickets if t[by] == group]
            if not group_tickets:
                continue
            prefix = 'milestone.stats.groups.%s' % group_no
            req.hdf['%s.name' % prefix] = group
            percent_total = 0
            if len(tickets) > 0:
                percent_total = float(len(group_tickets)) / float(len(tickets))
                if percent_total > max_percent_total:
                    max_percent_total = percent_total
            req.hdf['%s.percent_total' % prefix] = percent_total * 100
            stats = calc_ticket_stats(group_tickets)
            req.hdf[prefix] = stats
            for key, value in get_query_links(self.env, milestone.name,
                                              by, group).items():
                req.hdf['%s.queries.%s' % (prefix, key)] = escape(value)
            group_no += 1
        req.hdf['milestone.stats.max_percent_total'] = max_percent_total * 100

    # IWikiSyntaxProvider methods
    
    def get_wiki_syntax(self):
        return []
    
    def get_link_resolvers(self):
        yield ('milestone', self._format_link)

    def _format_link(self, formatter, ns, name, label):
        return '<a class="milestone" href="%s">%s</a>' \
               % (formatter.href.milestone(name), label)
