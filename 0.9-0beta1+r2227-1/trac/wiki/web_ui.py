# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003-2005 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgstr�m <jonas@edgewall.com>
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
# Author: Jonas Borgstr�m <jonas@edgewall.com>
#         Christopher Lenz <cmlenz@gmx.de>

from __future__ import generators
import re
import time
import StringIO

from trac.attachment import attachment_to_hdf, Attachment
from trac.core import *
from trac.perm import IPermissionRequestor
from trac.Search import ISearchSource, query_to_sql, shorten_result
from trac.Timeline import ITimelineEventProvider
from trac.util import enum, escape, get_reporter_id, pretty_timedelta, \
                      shorten_line
from trac.versioncontrol.diff import get_diff_options, hdf_diff
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.web import IRequestHandler
from trac.wiki.model import WikiPage
from trac.wiki.formatter import wiki_to_html, wiki_to_oneliner


class WikiModule(Component):

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler,
               ITimelineEventProvider, ISearchSource)

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'wiki'

    def get_navigation_items(self, req):
        if not req.perm.has_permission('WIKI_VIEW'):
            return
        yield 'metanav', 'help', '<a href="%s" accesskey="6">Help/Guide</a>' \
              % escape(self.env.href.wiki('TracGuide'))
        yield 'mainnav', 'wiki', '<a href="%s" accesskey="1">Wiki</a>' \
              % escape(self.env.href.wiki())

    # IPermissionRequestor methods

    def get_permission_actions(self):
        actions = ['WIKI_CREATE', 'WIKI_DELETE', 'WIKI_MODIFY', 'WIKI_VIEW']
        return actions + [('WIKI_ADMIN', actions)]

    # IRequestHandler methods

    def match_request(self, req):
        match = re.match(r'^/wiki(?:/(.*))?', req.path_info)
        if match:
            if match.group(1):
                req.args['page'] = match.group(1)
            return 1

    def process_request(self, req):
        action = req.args.get('action', 'view')
        pagename = req.args.get('page', 'WikiStart')
        version = req.args.get('version')

        db = self.env.get_db_cnx()
        page = WikiPage(self.env, pagename, version, db)

        add_stylesheet(req, 'common/css/wiki.css')

        if req.method == 'POST':
            if action == 'edit':
                latest_version = WikiPage(self.env, pagename, None, db).version
                if req.args.has_key('cancel'):
                    req.redirect(self.env.href.wiki(page.name))
                elif int(version) != latest_version:
                    print version, latest_version
                    action = 'collision'
                    self._render_editor(req, db, page)
                elif req.args.has_key('preview'):
                    action = 'preview'
                    self._render_editor(req, db, page, preview=True)
                else:
                    self._do_save(req, db, page)
            elif action == 'delete':
                self._do_delete(req, db, page)
            elif action == 'diff':
                get_diff_options(req)
                req.redirect(self.env.href.wiki(page.name, version=page.version,
                                                action='diff'))
        elif action == 'delete':
            self._render_confirm(req, db, page)
        elif action == 'edit':
            self._render_editor(req, db, page)
        elif action == 'diff':
            self._render_diff(req, db, page)
        elif action == 'history':
            self._render_history(req, db, page)
        else:
            if req.args.get('format') == 'txt':
                req.send_response(200)
                req.send_header('Content-Type', 'text/plain;charset=utf-8')
                req.end_headers()
                req.write(page.text)
                return
            self._render_view(req, db, page)

        req.hdf['wiki.action'] = action
        req.hdf['wiki.page_name'] = escape(page.name)
        req.hdf['wiki.current_href'] = escape(self.env.href.wiki(page.name))
        return 'wiki.cs', None

    # ITimelineEventProvider methods

    def get_timeline_filters(self, req):
        if req.perm.has_permission('WIKI_VIEW'):
            yield ('wiki', 'Wiki changes')

    def get_timeline_events(self, req, start, stop, filters):
        if 'wiki' in filters:
            format = req.args.get('format')
            db = self.env.get_db_cnx()
            cursor = db.cursor()
            cursor.execute("SELECT time,name,comment,author "
                           "FROM wiki WHERE time>=%s AND time<=%s",
                           (start, stop))
            for t,name,comment,author in cursor:
                title = '<em>%s</em> edited by %s' % (
                        escape(name), escape(author))
                if format == 'rss':
                    href = self.env.abs_href.wiki(name)
                    comment = wiki_to_html(comment or '--', self.env, db,
                                           absurls=True)
                else:
                    href = self.env.href.wiki(name)
                    comment = wiki_to_oneliner(shorten_line(comment), self.env,
                                               db)
                yield 'wiki', href, title, t, author, comment

    # Internal methods

    def _do_delete(self, req, db, page):
        if page.readonly:
            req.perm.assert_permission('WIKI_ADMIN')
        else:
            req.perm.assert_permission('WIKI_DELETE')

        if req.args.has_key('cancel'):
            req.redirect(self.env.href.wiki(page.name))

        version = None
        if req.args.has_key('delete_version'):
            version = int(req.args.get('version', 0))

        page.delete(version, db)
        db.commit()

        if not page.exists:
            req.redirect(self.env.href.wiki())
        else:
            req.redirect(self.env.href.wiki(page.name))

    def _do_save(self, req, db, page):
        if page.readonly:
            req.perm.assert_permission('WIKI_ADMIN')
        elif not page.exists:
            req.perm.assert_permission('WIKI_CREATE')
        else:
            req.perm.assert_permission('WIKI_MODIFY')

        page.text = req.args.get('text')
        if req.perm.has_permission('WIKI_ADMIN'):
            # Modify the read-only flag if it has been changed and the user is
            # WIKI_ADMIN
            page.readonly = int(req.args.has_key('readonly'))

        page.save(req.args.get('author'), req.args.get('comment'),
                  req.remote_addr)
        req.redirect(self.env.href.wiki(page.name))

    def _render_confirm(self, req, db, page):
        if page.readonly:
            req.perm.assert_permission('WIKI_ADMIN')
        else:
            req.perm.assert_permission('WIKI_DELETE')

        version = None
        if req.args.has_key('delete_version'):
            version = int(req.args.get('version', 0))

        req.hdf['title'] = escape(page.name) + ' (delete)'
        req.hdf['wiki'] = {'page_name': escape(page.name), 'mode': 'delete'}
        if version is not None:
            req.hdf['wiki.version'] = version
            num_versions = 0
            for change in page.get_history():
                num_versions += 1;
                if num_versions > 1:
                    break
            req.hdf['wiki.only_version'] = num_versions == 1

    def _render_diff(self, req, db, page):
        req.perm.assert_permission('WIKI_VIEW')

        if not page.exists:
            raise TracError, "Version %s of page %s does not exist" \
                             % (req.args.get('version'), page.name)

        add_stylesheet(req, 'common/css/diff.css')

        req.hdf['title'] = escape(page.name) + ' (diff)'

        # Ask web spiders to not index old versions
        req.hdf['html.norobots'] = 1

        old_version = req.args.get('old_version')
        if old_version:
            old_version = int(old_version)
            if old_version == page.version:
                old_version = None
            elif old_version > page.version:
                old_version, page = page.version, \
                                    WikiPage(self.env, page.name, old_version)

        info = {
            'version': page.version,
            'history_href': escape(self.env.href.wiki(page.name,
                                                      action='history'))
        }

        num_changes = 0
        old_page = None
        for version,t,author,comment,ipnr in page.get_history():
            if version == page.version:
                if t:
                    info['time'] = time.strftime('%c', time.localtime(int(t)))
                    info['time_delta'] = pretty_timedelta(t)
                info['author'] = escape(author or 'anonymous')
                info['comment'] = escape(comment or '--')
                info['ipnr'] = escape(ipnr or '')
            else:
                num_changes += 1
                if version < page.version:
                    if (old_version and version == old_version) or \
                            not old_version:
                        old_page = WikiPage(self.env, page.name, version)
                        info['num_changes'] = num_changes
                        info['old_version'] = version
                        break

        req.hdf['wiki'] = info

        diff_style, diff_options = get_diff_options(req)

        oldtext = old_page and old_page.text.splitlines() or []
        newtext = page.text.splitlines()
        context = 3
        for option in diff_options:
            if option.startswith('-U'):
                context = int(option[2:])
                break
        changes = hdf_diff(oldtext, newtext, context=context,
                           ignore_blank_lines='-B' in diff_options,
                           ignore_case='-i' in diff_options,
                           ignore_space_changes='-b' in diff_options)
        req.hdf['wiki.diff'] = changes

    def _render_editor(self, req, db, page, preview=False):
        req.perm.assert_permission('WIKI_MODIFY')

        if req.args.has_key('text'):
            page.text = req.args.get('text')
        if preview:
            page.readonly = req.args.has_key('readonly')

        author = req.args.get('author', get_reporter_id(req))
        comment = req.args.get('comment', '')
        editrows = req.args.get('editrows')
        if editrows:
            pref = req.session.get('wiki_editrows', '20')
            if editrows != pref:
                req.session['wiki_editrows'] = editrows
        else:
            editrows = req.session.get('wiki_editrows', '20')

        req.hdf['title'] = escape(page.name) + ' (edit)'
        info = {
            'page_source': escape(page.text),
            'version': page.version,
            'author': escape(author),
            'comment': escape(comment),
            'readonly': page.readonly,
            'edit_rows': editrows,
            'scroll_bar_pos': req.args.get('scroll_bar_pos', '')
        }
        if page.exists:
            info['history_href'] = escape(self.env.href.wiki(page.name,
                                                             action='history'))
        if preview:
            info['page_html'] = wiki_to_html(page.text, self.env, req, db)
            info['readonly'] = int(req.args.has_key('readonly'))
        req.hdf['wiki'] = info

    def _render_history(self, req, db, page):
        """Extract the complete history for a given page and stores it in the
        HDF.

        This information is used to present a changelog/history for a given
        page.
        """
        req.perm.assert_permission('WIKI_VIEW')

        if not page.exists:
            raise TracError, "Page %s does not exist" % page.name

        req.hdf['title'] = escape(page.name) + ' (history)'

        history = []
        for version, t, author, comment, ipnr in page.get_history():
            history.append({
                'url': escape(self.env.href.wiki(page.name, version=version)),
                'diff_url': escape(self.env.href.wiki(page.name,
                                                      version=version,
                                                      action='diff')),
                'version': version,
                'time': time.strftime('%x %X', time.localtime(int(t))),
                'time_delta': pretty_timedelta(t),
                'author': escape(author),
                'comment': wiki_to_oneliner(comment or '', self.env, db),
                'ipaddr': ipnr
            })
        req.hdf['wiki.history'] = history

    def _render_view(self, req, db, page):
        req.perm.assert_permission('WIKI_VIEW')

        if page.name == 'WikiStart':
            req.hdf['title'] = ''
        else:
            req.hdf['title'] = escape(page.name)

        version = req.args.get('version')
        if version:
            # Ask web spiders to not index old versions
            req.hdf['html.norobots'] = 1

        txt_href = self.env.href.wiki(page.name, version=version, format='txt')
        add_link(req, 'alternate', txt_href, 'Plain Text', 'text/plain')

        req.hdf['wiki'] = {'page_name': page.name, 'exists': page.exists,
                           'version': page.version, 'readonly': page.readonly}
        if page.exists:
            req.hdf['wiki.page_html'] = wiki_to_html(page.text, self.env, req)
            history_href = self.env.href.wiki(page.name, action='history')
            req.hdf['wiki.history_href'] = escape(history_href)
        else:
            if not req.perm.has_permission('WIKI_CREATE'):
                raise TracError('Page %s not found' % page.name)
            req.hdf['wiki.page_html'] = '<p>Describe "%s" here</p>' % page.name

        # Show attachments
        attachments = []
        for attachment in Attachment.select(self.env, 'wiki', page.name, db):
            attachments.append(attachment_to_hdf(self.env, db, req, attachment))
        req.hdf['wiki.attachments'] = attachments
        if req.perm.has_permission('WIKI_MODIFY'):
            attach_href = self.env.href.attachment('wiki', page.name)
            req.hdf['wiki.attach_href'] = attach_href

    # ISearchPrivider methods

    def get_search_filters(self, req):
        if req.perm.has_permission('WIKI_VIEW'):
            yield ('wiki', 'Wiki')

    def get_search_results(self, req, query, filters):
        if not 'wiki' in filters:
            return
        db = self.env.get_db_cnx()
        sql = "SELECT w1.name,w1.time,w1.author,w1.text " \
              "FROM wiki w1," \
              "(SELECT name,max(version) AS ver " \
              "FROM wiki GROUP BY name) w2 " \
              "WHERE w1.version = w2.ver AND w1.name = w2.name " \
              "AND (%s OR %s OR %s)" % \
              (query_to_sql(db, query, 'w1.name'),
               query_to_sql(db, query, 'w1.author'),
               query_to_sql(db, query, 'w1.text'))
        
        cursor = db.cursor()
        cursor.execute(sql)
        for name, date, author, text in cursor:
            yield (self.env.href.wiki(name),
                   '%s: %s' % (name, escape(shorten_line(text))),
                   date, author,
                   escape(shorten_result(text, query.split())))
