# -*- coding: iso8859-1 -*-
# 
# Copyright (C) 2003-2005 Edgewall Software
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

__copyright__ = 'Copyright (c) 2003-2005 Edgewall Software'

from __future__ import generators
import os
import os.path
import sys
import time
import cmd
import shlex
import shutil
import StringIO
import traceback
import urllib

import trac
from trac import perm, util, db_default
from trac.config import default_dir
from trac.env import Environment
from trac.config import Configuration
from trac.Milestone import Milestone
from trac.perm import PermissionSystem
from trac.ticket.model import *
from trac.wiki import WikiPage

try:
    sum
except NameError:
    def sum(list):
        """Python2.2 doesn't have sum()"""
        tot = 0
        for item in list:
            tot += item
        return tot


class TracAdmin(cmd.Cmd):
    intro = ''
    license = trac.__license_long__
    doc_header = 'Trac Admin Console %(ver)s\n' \
                 'Available Commands:\n' \
                 % {'ver':trac.__version__ }
    ruler = ''
    prompt = "Trac> "
    __env = None
    _date_format = '%Y-%m-%d'
    _datetime_format = '%Y-%m-%d %H:%M:%S'
    _date_format_hint = 'YYYY-MM-DD'

    def __init__(self, envdir=None):
        cmd.Cmd.__init__(self)
        self.interactive = 0
        if envdir:
            self.env_set(os.path.abspath(envdir))

    def docmd(self, cmd='help'):
        self.onecmd(cmd)

    def emptyline(self):
        pass

    def run(self):
        self.interactive = 1
        print 'Welcome to trac-admin %(ver)s\n'                \
              'Interactive Trac adminstration console.\n'       \
              '%(copy)s\n\n'                                    \
              "Type:  '?' or 'help' for help on commands.\n" %  \
              {'ver':trac.__version__,'copy':__copyright__}
        self.cmdloop()

    ##
    ## Environment methods
    ##

    def env_set(self, envname, env=None):
        self.envname = envname
        self.prompt = "Trac [%s]> " % self.envname
        if env is not None:
            self.__env = env

    def env_check(self):
        try:
            self.__env = Environment(self.envname)
        except:
            return 0
        return 1

    def env_create(self, db_str):
        try:
            self.__env = Environment(self.envname, create=True, db_str=db_str)
            return self.__env
        except Exception, e:
            print 'Failed to create environment.', e
            traceback.print_exc()
            sys.exit(1)

    def env_open(self):
        try:
            if not self.__env:
                self.__env = Environment(self.envname)
            return self.__env
        except Exception, e:
            print 'Failed to open environment.', e
            traceback.print_exc()
            sys.exit(1)

    def db_open(self):
        return self.env_open().get_db_cnx()

    def db_query(self, sql, cursor=None):
        if not cursor:
            cursor = self.db_open().cursor()
        cursor.execute(sql)
        for row in cursor:
            yield row

    def db_update(self, sql, cursor=None):
        if not cursor:
            cnx = self.db_open()
            cursor = cnx.cursor()
        else:
            cnx = None
        cursor.execute(sql)
        if cnx:
            cnx.commit()

    ##
    ## Utility methods
    ##

    def arg_tokenize (self, argstr):
        if hasattr(sys.stdin, 'encoding'): # Since version 2.3
            argstr = util.to_utf8(argstr, sys.stdin.encoding)
        if hasattr(shlex, 'split'):
            toks = shlex.split(argstr)
        else:
            def my_strip(s, c):
                """string::strip in python2.1 doesn't support arguments"""
                i = j = 0
                for i in range(len(s)):
                    if not s[i] in c:
                        break
                for j in range(len(s), 0, -1):
                    if not s[j-1] in c:
                        break
                return s[i:j]
        
            lexer = shlex.shlex(StringIO.StringIO(argstr))
            lexer.wordchars = lexer.wordchars + ".,_/"
            toks = []
            while 1:
                token = my_strip(lexer.get_token(), '"\'')
                if not token:
                    break
                toks.append(token)
        return toks or ['']

    def word_complete (self, text, words):
        return [a for a in words if a.startswith (text)]

    def print_listing(self, headers, data, sep=' ', decor=True):
        ldata = list(data)
        if decor:
            ldata.insert(0, headers)
        print
        colw = []
        ncols = len(ldata[0]) # assumes all rows are of equal length
        for cnum in xrange(0, ncols):
            mw = 0
            for cell in [str(d[cnum]) or '' for d in ldata]:
                if len(cell) > mw:
                    mw = len(cell)
            colw.append(mw)
        for rnum in xrange(len(ldata)):
            for cnum in xrange(ncols):
                if decor and rnum == 0:
                    sp = ('%%%ds' % len(sep)) % ' '  # No separator in header
                else:
                    sp = sep
                if cnum + 1 == ncols:
                    sp = '' # No separator after last column
                print ('%%-%ds%s' % (colw[cnum], sp)) \
                      % (ldata[rnum][cnum] or ''),
            print
            if rnum == 0 and decor:
                print ''.join(['-' for x in
                               xrange(0, (1 + len(sep)) * cnum + sum(colw))])
        print

    def print_doc(self, doc, decor=False):
        if not doc: return
        self.print_listing(['Command', 'Description'], doc, '  --', decor) 

    def get_component_list(self):
        rows = self.db_query("SELECT name FROM component")
        return [row[0] for row in rows]

    def get_user_list(self):
        rows = self.db_query("SELECT DISTINCT username FROM permission")
        return [row[0] for row in rows]

    def get_wiki_list(self):
        rows = self.db_query('SELECT DISTINCT name FROM wiki') 
        return [row[0] for row in rows]

    def get_dir_list(self, pathstr, justdirs=False):
        dname = os.path.dirname(pathstr)
        d = os.path.join(os.getcwd(), dname)
        dlist = os.listdir(d)
        if justdirs:
            result = []
            for entry in dlist:
                try:
                    if os.path.isdir(entry):
                        result.append(entry)
                except:
                    pass
        else:
            result = dlist
        return result

    def get_enum_list(self, type):
        rows = self.db_query("SELECT name FROM enum WHERE type='%s'" % type)
        return [row[0] for row in rows]

    def get_milestone_list(self):
        rows = self.db_query("SELECT name FROM milestone")
        return [row[0] for row in rows]

    def get_version_list(self):
        rows = self.db_query("SELECT name FROM version")
        return [row[0] for row in rows]

    def _parse_date(self, t):
        seconds = None
        t = t.strip()
        if t == 'now':
            seconds = int(time.time())
        else:
            for format in [self._date_format, '%x %X', '%x, %X', '%X %x', '%X, %x', '%x', '%c',
                           '%b %d, %Y']:
                try:
                    pt = time.strptime(t, format)
                    seconds = int(time.mktime(pt))
                except ValueError:
                    continue
                break
        if seconds == None:
            try:
                seconds = int(t)
            except ValueError:
                pass
        if seconds == None:
            print >> sys.stderr, 'Unknown time format'
        return seconds

    def _format_date(self, s):
        return time.strftime(self._date_format, time.localtime(s))

    def _format_datetime(self, s):
        return time.strftime(self._datetime_format, time.localtime(s))


    ##
    ## Available Commands
    ##

    ## Help
    _help_help = [('help', 'Show documentation')]

    def do_help(self, line=None):
        arg = self.arg_tokenize(line)
        if arg[0]:
            try:
                doc = getattr(self, "_help_" + arg[0])
                self.print_doc (doc)
            except AttributeError:
                print "No documentation found for '%s'" % arg[0]
        else:
            docs = (self._help_about + self._help_help +
                    self._help_initenv + self._help_hotcopy +
                    self._help_resync + self._help_upgrade +
                    self._help_wiki +
#                    self._help_config + self._help_wiki +
                    self._help_permission + self._help_component +
                    self._help_ticket_type + self._help_priority +
                    self._help_severity +  self._help_version +
                    self._help_milestone)
            print 'trac-admin - The Trac Administration Console %s' % trac.__version__
            if not self.interactive:
                print
                print "Usage: trac-admin </path/to/projenv> [command [subcommand] [option ...]]\n"
                print "Invoking trac-admin without command starts "\
                       "interactive mode."
            self.print_doc (docs)

    
    ## About / Version
    _help_about = [('about', 'Shows information about trac-admin')]

    def do_about(self, line):
        print
        print 'Trac Admin Console %s' % trac.__version__
        print '================================================================='
        print self.license


    ## Quit / EOF
    _help_quit = [['quit', 'Exit the program']]
    _help_exit = _help_quit
    _help_EOF = _help_quit

    def do_quit(self, line):
        print
        sys.exit()

    do_exit = do_quit # Alias
    do_EOF = do_quit # Alias


    # Component
    _help_component = [('component list', 'Show available components'),
                       ('component add <name> <owner>', 'Add a new component'),
                       ('component rename <name> <newname>',
                        'Rename a component'),
                       ('component remove <name>',
                        'Remove/uninstall component'),
                       ('component chown <name> <owner>',
                        'Change component ownership')]

    def complete_component(self, text, line, begidx, endidx):
        if begidx in (16, 17):
            comp = self.get_component_list()
        elif begidx > 15 and line.startswith('component chown '):
            comp = self.get_user_list()
        else:
            comp = ['list', 'add', 'rename', 'remove', 'chown']
        return self.word_complete(text, comp)

    def do_component(self, line):
        arg = self.arg_tokenize(line)
        try:
            if arg[0]  == 'list':
                self._do_component_list()
            elif arg[0] == 'add' and len(arg)==3:
                name = arg[1]
                owner = arg[2]
                self._do_component_add(name, owner)
            elif arg[0] == 'rename' and len(arg)==3:
                name = arg[1]
                newname = arg[2]
                self._do_component_rename(name, newname)
            elif arg[0] == 'remove'  and len(arg)==2:
                name = arg[1]
                self._do_component_remove(name)
            elif arg[0] == 'chown' and len(arg)==3:
                name = arg[1]
                owner = arg[2]
                self._do_component_set_owner(name, owner)
            else:    
                self.do_help ('component')
        except Exception, e:
            print 'Component %s failed:' % arg[0], e

    def _do_component_list(self):
        data = []
        for c in Component.select(self.env_open()):
            data.append((c.name, c.owner))
        self.print_listing(['Name', 'Owner'], data)

    def _do_component_add(self, name, owner):
        component = Component(self.env_open())
        component.name = name
        component.owner = owner
        component.insert()

    def _do_component_rename(self, name, newname):
        component = Component(self.env_open(), name)
        component.name = newname
        component.update()

    def _do_component_remove(self, name):
        component = Component(self.env_open(), name)
        component.delete()

    def _do_component_set_owner(self, name, owner):
        component = Component(self.env_open(), name)
        component.owner = owner
        component.update()


    ## Permission
    _help_permission = [('permission list [user]', 'List permission rules'),
                        ('permission add <user> <action> [action] [...]',
                         'Add a new permission rule'),
                        ('permission remove <user> <action> [action] [...]',
                         'Remove permission rule')]

    def complete_permission(self, text, line, begidx, endidx):
        argv = self.arg_tokenize(line)
        argc = len(argv)
        if line[-1] == ' ': # Space starts new argument
            argc += 1
        if argc == 2:
            comp = ['list', 'add', 'remove']
        elif argc >= 4:
            comp = perm.permissions + perm.meta_permissions.keys()
            comp.sort()
        return self.word_complete(text, comp)

    def do_permission(self, line):
        arg = self.arg_tokenize(line)
        try:
            if arg[0]  == 'list':
                user = None
                if len(arg) > 1:
                    user = arg[1]
                self._do_permission_list(user)
            elif arg[0] == 'add' and len(arg) >= 3:
                user = arg[1]
                for action in arg[2:]:
                    self._do_permission_add(user, action)
            elif arg[0] == 'remove'  and len(arg) >= 3:
                user = arg[1]
                for action in arg[2:]:
                    self._do_permission_remove(user, action)
            else:
                self.do_help('permission')
        except Exception, e:
            print 'Permission %s failed:' % arg[0], e

    def _do_permission_list(self, user=None):
        if user:
            rows = self.db_query("SELECT username, action FROM permission "
                                 "WHERE username='%s' ORDER BY action" % user)
        else:
            rows = self.db_query("SELECT username, action FROM permission "
                                 "ORDER BY username, action")
        self.print_listing(['User', 'Action'], rows)
        print
        print 'Available actions:'
        actions = PermissionSystem(self.env_open()).get_actions()
        actions.sort()
        text = ', '.join(actions)
        print util.wrap(text, initial_indent=' ', subsequent_indent=' ',
                        linesep='\n')
        print

    def _do_permission_add(self, user, action):
        if not action.islower() and not action.isupper():
            print 'Group names must be in lower case and actions in upper case'
            return
        self.db_update("INSERT INTO permission VALUES('%s', '%s')"
                       % (user, action))

    def _do_permission_remove(self, user, action):
        sql = "DELETE FROM permission"
        clauses = []
        if action != '*':
            clauses.append("action='%s'" % action)
        if user != '*':
            clauses.append("username='%s'" % user)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        self.db_update(sql)


    ## Initenv
    _help_initenv = [('initenv',
                      'Create and initialize a new environment interactively'),
                     ('initenv <projectname> <db> <repospath> <templatepath>',
                      'Create and initialize a new environment from arguments')]

    def do_initdb(self, line):
        self.do_initenv(line)

    def get_initenv_args(self):
        returnvals = []
        print 'Creating a new Trac environment at %s' % self.envname
        print
        print 'Trac will first ask a few questions about your environment '
        print 'in order to initalize and prepare the project database.'
        print
        print " Please enter the name of your project."
        print " This name will be used in page titles and descriptions."
        print
        dp = 'My Project'
        returnvals.append(raw_input('Project Name [%s]> ' % dp).strip() or dp)
        print
        print ' Please specify the connection string for the database to use.'
        print ' By default, a local SQLite database is created in the environment '
        print ' directory. It is also possible to use an already existing '
        print ' PostgreSQL database (check the Trac documentation for the exact '
        print ' connection string syntax).'
        print
        ddb = 'sqlite:db/trac.db'
        prompt = 'Database connection string [%s]> ' % ddb
        returnvals.append(raw_input(prompt).strip()  or ddb)
        print
        print ' Please specify the absolute path to the project Subversion repository.'
        print ' Repository must be local, and trac-admin requires read+write'
        print ' permission to initialize the Trac database.'
        print
        drp = '/var/svn/test'
        prompt = 'Path to repository [%s]> ' % drp
        returnvals.append(raw_input(prompt).strip()  or drp)
        print
        print ' Please enter location of Trac page templates.'
        print ' Default is the location of the site-wide templates installed with Trac.'
        print
        dt = default_dir('templates')
        prompt = 'Templates directory [%s]> ' % dt
        returnvals.append(raw_input(prompt).strip()  or dt)
        return returnvals

    def do_initenv(self, line):
        if self.env_check():
            print "Initenv for '%s' failed." % self.envname
            print "Does an environment already exist?"
            return
        arg = self.arg_tokenize(line)
        project_name = None
        db_str = None
        repository_dir = None
        templates_dir = None
        if len(arg) == 1 and not arg[0]:
            returnvals = self.get_initenv_args()
            project_name, db_str, repository_dir, templates_dir = returnvals
        elif len(arg) != 4:
            print 'Wrong number of arguments to initenv: %d' % len(arg)
            return
        else:
            project_name, db_str, repository_dir, templates_dir = arg[:4]

        if not os.access(os.path.join(templates_dir, 'header.cs'), os.F_OK):
            print templates_dir, "doesn't look like a Trac templates directory"
            return
        try:
            print 'Creating and Initializing Project'
            self.env_create(db_str)

            print ' Configuring Project'
            config = self.__env.config
            print '  trac.repository_dir'
            config.set('trac', 'repository_dir', repository_dir)
            print '  trac.database'
            config.set('trac', 'database', db_str)
            print '  trac.templates_dir'
            config.set('trac', 'templates_dir', templates_dir)
            print '  project.name'
            config.set('project', 'name', project_name)
            config.save()

            # Add the default wiki macros
            print ' Installing default wiki macros'
            for f in os.listdir(default_dir('macros')):
                if not f.endswith('.py'):
                    continue
                src = os.path.join(default_dir('macros'), f)
                dst = os.path.join(self.__env.path, 'wiki-macros', f)
                print " %s => %s" % (src, f)
                shutil.copy2(src, dst)

            # Add a few default wiki pages
            print ' Installing default wiki pages'
            cnx = self.__env.get_db_cnx()
            cursor = cnx.cursor()
            self._do_wiki_load(default_dir('wiki'), cursor)
            cnx.commit()

            print ' Indexing repository'
            repos = self.__env.get_repository()
            repos.sync()

        except Exception, e:
            print 'Failed to initialize environment.', e
            traceback.print_exc()
            sys.exit(2)


        print "---------------------------------------------------------------------"
        print
        print 'Project database for \'%s\' created.' % project_name
        print
        print ' Customize settings for your project using the command:'
        print
        print '   trac-admin %s' % self.envname
        print
        print ' Don\'t forget, you also need to copy (or symlink) "trac/cgi-bin/trac.cgi"'
        print ' to you web server\'s /cgi-bin/ directory, and then configure the server.'
        print
        print ' If you\'re using Apache, this config example snippet might be helpful:'
        print
        print '    Alias /trac "/wherever/you/installed/trac/htdocs/"'
        print '    <Location "/cgi-bin/trac.cgi">'
        print '        SetEnv TRAC_ENV "%s"' % self.envname
        print '    </Location>'
        print
        print '    # You need something like this to authenticate users'
        print '    <Location "/cgi-bin/trac.cgi/login">'
        print '        AuthType Basic'
        print '        AuthName "%s"' % project_name
        print '        AuthUserFile /somewhere/trac.htpasswd'
        print '        Require valid-user'
        print '    </Location>'
        print

        print ' The latest documentation can also always be found on the project website:'
        print ' http://projects.edgewall.com/trac/'
        print
        print 'Congratulations!'
        print
        
    _help_resync = [('resync', 'Re-synchronize trac with the repository')]

    ## Resync
    def do_resync(self, line):
        print 'resyncing...'
        cnx = self.db_open() # We need to call this function to open the env, really stupid
        self.db_update("DELETE FROM revision")
        self.db_update("DELETE FROM node_change")

        repos = self.__env.get_repository()
        repos.sync()
            
        print 'done.'


    ## Wiki
    _help_wiki = [('wiki list', 'List wiki pages'),
                  ('wiki remove <name>', 'Remove wiki page'),
                  ('wiki export <page> [file]',
                   'Export wiki page to file or stdout'),
                  ('wiki import <page> [file]',
                   'Import wiki page from file or stdin'),
                  ('wiki dump <directory>',
                   'Export all wiki pages to files named by title'),
                  ('wiki load <directory>',
                   'Import all wiki pages from directory'),
                  ('wiki upgrade',
                   'Upgrade default wiki pages to current version')]

    def complete_wiki(self, text, line, begidx, endidx):
        argv = self.arg_tokenize(line)
        argc = len(argv)
        if line[-1] == ' ': # Space starts new argument
            argc += 1
        if argc == 2:
            comp = ['list', 'remove', 'import', 'export', 'dump', 'load',
                    'upgrade']
        else:
            if argv[1] in ('dump', 'load'):
                comp = self.get_dir_list(argv[-1], 1)
            elif argv[1] == 'remove':
                comp = self.get_wiki_list()
            elif argv[1] in ('export', 'import'):
                if argc == 3:
                    comp = self.get_wiki_list()
                elif argc == 4:
                    comp = self.get_dir_list(argv[-1])
        return self.word_complete(text, comp)

    def do_wiki(self, line):
        arg = self.arg_tokenize(line)
        try:
            if arg[0]  == 'list':
                self._do_wiki_list()
            elif arg[0] == 'remove'  and len(arg)==2:
                name = arg[1]
                self._do_wiki_remove(name)
            elif arg[0] == 'import' and len(arg) == 3:
                title = arg[1]
                file = arg[2]
                self._do_wiki_import(file, title)
            elif arg[0] == 'export'  and len(arg) in [2,3]:
                page = arg[1]
                file = (len(arg) == 3 and arg[2]) or None
                self._do_wiki_export(page, file)
            elif arg[0] == 'dump' and len(arg) in [1,2]:
                dir = (len(arg) == 2 and arg[1]) or ''
                self._do_wiki_dump(dir)
            elif arg[0] == 'load' and len(arg) in [1,2]:
                dir = (len(arg) == 2 and arg[1]) or ''
                self._do_wiki_load(dir)
            elif arg[0] == 'upgrade' and len(arg) == 1:
                self._do_wiki_load(default_dir('wiki'),
                                   ignore=['WikiStart', 'checkwiki.py'])
            else:    
                self.do_help ('wiki')
        except Exception, e:
            print 'Wiki %s failed:' % arg[0], e

    def _do_wiki_list(self):
        rows = self.db_query("SELECT name,max(version),time "
                             "FROM wiki GROUP BY name ORDER BY name")
        self.print_listing(['Title', 'Edits', 'Modified'],
                           [(r[0], r[1], self._format_datetime(r[2])) for r in rows])

    def _do_wiki_remove(self, name):
        page = WikiPage(self.env_open(), name)
        page.delete()

    def _do_wiki_import(self, filename, title, cursor=None):
        if not os.path.isfile(filename):
            print "%s is not a file" % filename
            return
        f = open(filename,'r')
        data = util.to_utf8(f.read())

        # Make sure we don't insert the exact same page twice
        rows = self.db_query("SELECT text FROM wiki WHERE name='%s' "
                             "ORDER BY version DESC LIMIT 1" % title, cursor)
        old = list(rows)
        if old and data == old[0][0]:
            print '  %s already up to date.' % title
            return

        data = data.replace("'", "''") # Escape ' for safe SQL
        f.close()

        sql = ("INSERT INTO wiki(version,name,time,author,ipnr,text) "
               " SELECT 1+COALESCE(max(version),0),'%(title)s','%(time)s',"
               " '%(author)s','%(ipnr)s','%(text)s' FROM wiki "
               " WHERE name='%(title)s'" 
               % {'title':title,
                  'time':int(time.time()),
                  'author':'trac',
                  'ipnr':'127.0.0.1',
                  'locked':'0',
                  'text':data})
        self.db_update(sql, cursor)

    def _do_wiki_export(self, page, filename=''):
        data = self.db_query("SELECT text FROM wiki WHERE name='%s' "
                             "ORDER BY version DESC LIMIT 1" % page)
        text = data.next()[0]
        if not filename:
            print text
        else:
            if os.path.isfile(filename):
                raise Exception("File '%s' exists" % filename)
            f = open(filename,'w')
            f.write(text)
            f.close()

    def _do_wiki_dump(self, dir):
        pages = self.get_wiki_list()
        for p in pages:
            dst = os.path.join(dir, urllib.quote(p, ''))
            print " %s => %s" % (p, dst)
            self._do_wiki_export(p, dst)

    def _do_wiki_load(self, dir, cursor=None, ignore=[]):
        for page in os.listdir(dir):
            if page in ignore:
                continue
            filename = os.path.join(dir, page)
            page = urllib.unquote(page)
            if os.path.isfile(filename):
                print " %s => %s" % (filename, page)
                self._do_wiki_import(filename, page, cursor)


    ## (Ticket) Type
    _help_ticket_type = [('ticket_type list', 'Show possible ticket types'),
                         ('ticket_type add <value>', 'Add a ticket type'),
                         ('ticket_type change <value> <newvalue>',
                          'Change a ticket type'),
                         ('ticket_type remove <value>', 'Remove a ticket type')]
 
    def complete_ticket_type (self, text, line, begidx, endidx):
        if begidx == 16:
            comp = self.get_enum_list ('ticket_type')
        elif begidx < 15:
            comp = ['list', 'add', 'change', 'remove']
        return self.word_complete(text, comp)
 
    def do_ticket_type(self, line):
        self._do_enum('ticket_type', line)
 
    ## (Ticket) Priority
    _help_priority = [('priority list', 'Show possible ticket priorities'),
                       ('priority add <value>', 'Add a priority value option'),
                       ('priority change <value> <newvalue>',
                        'Change a priority value'),
                       ('priority remove <value>', 'Remove priority value')]

    def complete_priority (self, text, line, begidx, endidx):
        if begidx == 16:
            comp = self.get_enum_list ('priority')
        elif begidx < 15:
            comp = ['list', 'add', 'change', 'remove']
        return self.word_complete(text, comp)

    def do_priority(self, line):
        self._do_enum('priority', line)

    ## (Ticket) Severity
    _help_severity = [('severity list', 'Show possible ticket severities'),
                      ('severity add <value>', 'Add a severity value option'),
                      ('severity change <value> <newvalue>',
                       'Change a severity value'),
                      ('severity remove <value>', 'Remove severity value')]

    def complete_severity (self, text, line, begidx, endidx):
        if begidx == 16:
            comp = self.get_enum_list ('severity')
        elif begidx < 15:
            comp = ['list', 'add', 'change', 'remove']
        return self.word_complete(text, comp)

    def do_severity(self, line):
        self._do_enum('severity', line)

    # Type, priority, severity share the same datastructure and methods:

    _enum_map = {'ticket_type': Type, 'priority': Priority,
                 'severity': Severity}

    def _do_enum(self, type, line):
        arg = self.arg_tokenize(line)
        try:
            if arg[0]  == 'list':
                self._do_enum_list(type)
            elif arg[0] == 'add' and len(arg)==2:
                name = arg[1]
                self._do_enum_add(type, name)
            elif arg[0] == 'change'  and len(arg)==3:
                name = arg[1]
                newname = arg[2]
                self._do_enum_change(type, name, newname)
            elif arg[0] == 'remove'  and len(arg)==2:
                name = arg[1]
                self._do_enum_remove(type, name)
            else:    
                self.do_help (type)
        except Exception, e:
            print 'Command %s failed:' % arg[0], e

    def _do_enum_list(self, type):
        enum_cls = self._enum_map[type]
        self.print_listing(['Possible Values'],
                           [(e.name,) for e in enum_cls.select(self.env_open())])

    def _do_enum_add(self, type, name):
        sql = ("INSERT INTO enum(value,type,name) "
               " SELECT 1+COALESCE(max(value),0),'%(type)s','%(name)s'"
               "   FROM enum WHERE type='%(type)s'" 
               % {'type':type, 'name':name})
        self.db_update(sql)

    def _do_enum_change(self, type, name, newname):
        enum_cls = self._enum_map[type]
        enum = enum_cls(self.env_open(), name)
        enum.name = newname
        enum.update()

    def _do_enum_remove(self, type, name):
        enum_cls = self._enum_map[type]
        enum = enum_cls(self.env_open(), name)
        enum.delete()


    ## Milestone
    _help_milestone = [('milestone list', 'Show milestones'),
                       ('milestone add <name> [due]', 'Add milestone'),
                       ('milestone rename <name> <newname>',
                        'Rename milestone'),
                       ('milestone due <name> <due>',
                        'Set milestone due date (Format: "%s" or "now")'
                        % _date_format_hint),
                       ('milestone completed <name> <completed>',
                        'Set milestone completed date (Format: "%s" or "now")'
                        % _date_format_hint),
                       ('milestone remove <name>', 'Remove milestone')]

    def complete_milestone (self, text, line, begidx, endidx):
        if begidx in (15, 17):
            comp = self.get_milestone_list()
        elif begidx < 15:
            comp = ['list', 'add', 'rename', 'time', 'remove']
        return self.word_complete(text, comp)

    def do_milestone(self, line):
        arg = self.arg_tokenize(line)
        try:
            if arg[0]  == 'list':
                self._do_milestone_list()
            elif arg[0] == 'add' and len(arg) in [2,3]:
                self._do_milestone_add(arg[1])
                if len(arg) == 3:
                    self._do_milestone_set_due(arg[1], arg[2])
            elif arg[0] == 'rename' and len(arg) == 3:
                self._do_milestone_rename(arg[1], arg[2])
            elif arg[0] == 'remove' and len(arg) == 2:
                self._do_milestone_remove(arg[1])
            elif arg[0] == 'due' and len(arg) == 3:
                self._do_milestone_set_due(arg[1], arg[2])
            elif arg[0] == 'completed' and len(arg) == 3:
                self._do_milestone_set_completed(arg[1], arg[2])
            else:
                self.do_help('milestone')
        except Exception, e:
            print 'Command %s failed:' % arg[0], e

    def _do_milestone_list(self):
        data = []
        for m in Milestone.select(self.env_open()):
            data.append((m.name, m.due and self._format_date(m.due),
                         m.completed and self._format_datetime(m.completed)))

        self.print_listing(['Name', 'Due', 'Completed'], data)

    def _do_milestone_rename(self, name, newname):
        milestone = Milestone(self.env_open(), name)
        milestone.name = newname
        milestone.update()

    def _do_milestone_add(self, name):
        milestone = Milestone(self.env_open())
        milestone.name = name
        milestone.insert()

    def _do_milestone_remove(self, name):
        milestone = Milestone(self.env_open(), name)
        milestone.delete()

    def _do_milestone_set_due(self, name, t):
        milestone = Milestone(self.env_open(), name)
        milestone.due = self._parse_date(t)
        milestone.update()

    def _do_milestone_set_completed(self, name, t):
        milestone = Milestone(self.env_open(), name)
        milestone.completed = self._parse_date(t)
        milestone.update()

    ## Version
    _help_version = [('version list', 'Show versions'),
                       ('version add <name> [time]', 'Add version'),
                       ('version rename <name> <newname>',
                        'Rename version'),
                       ('version time <name> <time>',
                        'Set version date (Format: "%s" or "now")'
                        % _date_format_hint),
                       ('version remove <name>', 'Remove version')]

    def complete_version (self, text, line, begidx, endidx):
        if begidx in (13, 15):
            comp = self.get_version_list()
        elif begidx < 13:
            comp = ['list', 'add', 'rename', 'time', 'remove']
        return self.word_complete(text, comp)

    def do_version(self, line):
        arg = self.arg_tokenize(line)
        try:
            if arg[0]  == 'list':
                self._do_version_list()
            elif arg[0] == 'add' and len(arg) in [2,3]:
                self._do_version_add(arg[1])
                if len(arg) == 3:
                    self._do_version_time(arg[1], arg[2])
            elif arg[0] == 'rename' and len(arg) == 3:
                self._do_version_rename(arg[1], arg[2])
            elif arg[0] == 'time' and len(arg) == 3:
                self._do_version_time(arg[1], arg[2])
            elif arg[0] == 'remove' and len(arg) == 2:
                self._do_version_remove(arg[1])
            else:
                self.do_help('version')
        except Exception, e:
            print 'Command %s failed:' % arg[0], e

    def _do_version_list(self):
        data = []
        for v in Version.select(self.env_open()):
            data.append((v.name, v.time and self._format_date(v.time)))
        self.print_listing(['Name', 'Time'], data)

    def _do_version_rename(self, name, newname):
        version = Version(self.env_open(), name)
        version.name = newname
        version.update()

    def _do_version_add(self, name):
        version = Version(self.env_open())
        version.name = name
        version.insert()

    def _do_version_remove(self, name):
        version = Version(self.env_open(), name)
        version.delete()

    def _do_version_time(self, name, t):
        version = Version(self.env_open(), name)
        version.time = self._parse_date(t)
        version.update()

    _help_upgrade = [('upgrade', 'Upgrade database to current version')]
    def do_upgrade(self, line):
        arg = self.arg_tokenize(line)
        do_backup = True
        if arg[0] in ['-b', '--no-backup']:
            do_backup = False
        self.db_open()
        self._update_sample_config()
        try:
            if not self.__env.needs_upgrade():
                print "Database is up to date, no upgrade necessary."
                return
            self.__env.upgrade(backup=do_backup)
            print 'Upgrade done.'
        except Exception, e:
            print "Upgrade failed:", e
            traceback.print_exc()

    def _update_sample_config(self):
        filename = os.path.join(self.__env.path, 'conf', 'trac.ini.sample')
        try:
            file(filename, 'w').close() # Create the config file
            config = Configuration(filename)
            for section, name, value in db_default.default_config:
                config.set(section, name, value)
            config.save()
        except IOError, e:
            print "Warning: couldn't write sample configuration file (%s)" % e

    _help_hotcopy = [('hotcopy <backupdir>',
                      'Make a hot backup copy of an environment')]
    def do_hotcopy(self, line):
        arg = self.arg_tokenize(line)
        if arg[0]:
            dest = arg[0]
        else:
            self.do_help('hotcopy')
            return
        cnx = self.db_open()
        # Lock the database while copying files
        cnx.db.execute("BEGIN")
        print 'Hotcopying %s to %s ...' % (self.__env.path, dest),
        try:
            shutil.copytree(self.__env.path, dest, symlinks=1)
            print 'OK'
        except Exception, err:
            print err
        # Unlock database
        cnx.db.execute("ROLLBACK")

## ---------------------------------------------------------------------------

##
## Main
##

def run(*args):
    args = list(args)
    tracadm = TracAdmin()
    if len (args) > 0:
        if args[0] in ('-h', '--help', 'help'):
            tracadm.docmd("help")
        elif args[0] in ('-v','--version','about'):
            tracadm.docmd("about")
        else:
            tracadm.env_set(os.path.abspath(args[0]))
            if len (args) > 1:
                s_args = ' '.join(["'%s'" % c for c in args[2:]])
                command = args[1] + ' ' +s_args
                tracadm.docmd(command)
            else:
                while 1:
                    tracadm.run()
    else:
        tracadm.docmd ("help")
