# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2004 Edgewall Software
# Copyright (C) 2004 Daniel Lundin
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
# Author: Daniel Lundin <daniel@edgewall.com>

"""Trac support for Textile
See also: http://dealmeida.net/projects/textile/
"""

from trac.core import *
from trac.mimeview.api import IHTMLPreviewRenderer


class TextileRenderer(Component):
    """
    Renders plain text in Textile format as HTML.
    """
    implements(IHTMLPreviewRenderer)

    def get_quality_ratio(self, mimetype):
        if mimetype == 'text/x-textile':
            return 8
        return 0

    def render(self, req, mimetype, content, filename=None, rev=None):
        import textile
        return textile.textile(content)
