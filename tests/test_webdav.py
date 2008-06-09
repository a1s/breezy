# Copyright (C) 2008 Canonical Ltd
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

"""Tests for the wedav plugin."""

from cStringIO import StringIO
import stat


from bzrlib import (
    errors,
    tests,
    )
from bzrlib.plugins.webdav import webdav


def _get_list_dir_apache2_depth_1_prop():
    return """<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:" xmlns:ns0="DAV:">
    <D:response>
        <D:href>/19016477731212686926.835527/</D:href>
        <D:propstat>
            <D:prop>
            </D:prop>
            <D:status>HTTP/1.1 200 OK</D:status>
        </D:propstat>
    </D:response>
    <D:response>
        <D:href>/19016477731212686926.835527/a</D:href>
        <D:propstat>
            <D:prop>
            </D:prop>
            <D:status>HTTP/1.1 200 OK</D:status>
        </D:propstat>
    </D:response>
    <D:response>
        <D:href>/19016477731212686926.835527/b</D:href>
        <D:propstat>
            <D:prop>
            </D:prop>
            <D:status>HTTP/1.1 200 OK</D:status>
        </D:propstat>
    </D:response>
    <D:response>
        <D:href>/19016477731212686926.835527/c/</D:href>
        <D:propstat>
            <D:prop>
            </D:prop>
            <D:status>HTTP/1.1 200 OK</D:status>
        </D:propstat>
    </D:response>
</D:multistatus>"""


def _get_list_dir_apache2_depth_1_allprop():
    return """<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:" xmlns:ns0="DAV:">
    <D:response xmlns:lp1="DAV:" xmlns:lp2="http://apache.org/dav/props/">
        <D:href>/</D:href>
        <D:propstat>
            <D:prop>
                <lp1:resourcetype><D:collection/></lp1:resourcetype>
                <lp1:creationdate>2008-06-08T10:50:38Z</lp1:creationdate>
                <lp1:getlastmodified>Sun, 08 Jun 2008 10:50:38 GMT</lp1:getlastmodified>
                <lp1:getetag>"da7f5a-cc-7722db80"</lp1:getetag>
                <D:supportedlock>
                    <D:lockentry>
                        <D:lockscope><D:exclusive/></D:lockscope>
                        <D:locktype><D:write/></D:locktype>
                    </D:lockentry>
                    <D:lockentry>
                        <D:lockscope><D:shared/></D:lockscope>
                        <D:locktype><D:write/></D:locktype>
                    </D:lockentry>
                </D:supportedlock>
                <D:lockdiscovery/>
            </D:prop>
            <D:status>HTTP/1.1 200 OK</D:status>
        </D:propstat>
    </D:response>
    <D:response xmlns:lp1="DAV:" xmlns:lp2="http://apache.org/dav/props/">
        <D:href>/executable</D:href>
        <D:propstat>
            <D:prop>
                <lp1:resourcetype/>
                <lp1:creationdate>2008-06-08T09:50:15Z</lp1:creationdate>
                <lp1:getcontentlength>14</lp1:getcontentlength>
                <lp1:getlastmodified>Sun, 08 Jun 2008 09:50:11 GMT</lp1:getlastmodified>
                <lp1:getetag>"da9f81-0-9ef33ac0"</lp1:getetag>
                <lp2:executable>T</lp2:executable>
                <D:supportedlock>
                    <D:lockentry>
                        <D:lockscope><D:exclusive/></D:lockscope>
                        <D:locktype><D:write/></D:locktype>
                    </D:lockentry>
                    <D:lockentry>
                        <D:lockscope><D:shared/></D:lockscope>
                        <D:locktype><D:write/></D:locktype>
                    </D:lockentry>
                </D:supportedlock>
                <D:lockdiscovery/>
            </D:prop>
            <D:status>HTTP/1.1 200 OK</D:status>
        </D:propstat>
    </D:response>
    <D:response xmlns:lp1="DAV:" xmlns:lp2="http://apache.org/dav/props/">
        <D:href>/read-only</D:href>
        <D:propstat>
            <D:prop>
                <lp1:resourcetype/>
                <lp1:creationdate>2008-06-08T09:50:11Z</lp1:creationdate>
                <lp1:getcontentlength>42</lp1:getcontentlength>
                <lp1:getlastmodified>Sun, 08 Jun 2008 09:50:11 GMT</lp1:getlastmodified>
                <lp1:getetag>"da9f80-0-9ef33ac0"</lp1:getetag>
                <lp2:executable>F</lp2:executable>
                <D:supportedlock>
                    <D:lockentry>
                        <D:lockscope><D:exclusive/></D:lockscope>
                        <D:locktype><D:write/></D:locktype>
                    </D:lockentry>
                    <D:lockentry>
                        <D:lockscope><D:shared/></D:lockscope>
                        <D:locktype><D:write/></D:locktype>
                    </D:lockentry>
                </D:supportedlock>
                <D:lockdiscovery/>
            </D:prop>
            <D:status>HTTP/1.1 200 OK</D:status>
        </D:propstat>
    </D:response>
    <D:response xmlns:lp1="DAV:" xmlns:lp2="http://apache.org/dav/props/">
        <D:href>/titi</D:href>
        <D:propstat>
            <D:prop>
                <lp1:resourcetype/>
                <lp1:creationdate>2008-06-08T09:49:53Z</lp1:creationdate>
                <lp1:getcontentlength>6</lp1:getcontentlength>
                <lp1:getlastmodified>Sun, 08 Jun 2008 09:49:53 GMT</lp1:getlastmodified>
                <lp1:getetag>"da8cbc-6-9de09240"</lp1:getetag>
                <lp2:executable>F</lp2:executable>
                <D:supportedlock>
                    <D:lockentry>
                        <D:lockscope><D:exclusive/></D:lockscope>
                        <D:locktype><D:write/></D:locktype>
                    </D:lockentry>
                    <D:lockentry>
                        <D:lockscope><D:shared/></D:lockscope>
                        <D:locktype><D:write/></D:locktype>
                    </D:lockentry>
                </D:supportedlock>
                <D:lockdiscovery/>
            </D:prop>
            <D:status>HTTP/1.1 200 OK</D:status>
        </D:propstat>
    </D:response>
    <D:response xmlns:lp1="DAV:" xmlns:lp2="http://apache.org/dav/props/">
        <D:href>/toto/</D:href>
        <D:propstat>
            <D:prop>
                <lp1:resourcetype><D:collection/></lp1:resourcetype>
                <lp1:creationdate>2008-06-06T08:07:07Z</lp1:creationdate>
                <lp1:getlastmodified>Fri, 06 Jun 2008 08:07:07 GMT</lp1:getlastmodified>
                <lp1:getetag>"da8cb9-44-f2ac20c0"</lp1:getetag>
                <D:supportedlock>
                    <D:lockentry>
                        <D:lockscope><D:exclusive/></D:lockscope>
                        <D:locktype><D:write/></D:locktype>
                    </D:lockentry>
                    <D:lockentry>
                        <D:lockscope><D:shared/></D:lockscope>
                        <D:locktype><D:write/></D:locktype>
                    </D:lockentry>
                </D:supportedlock>
                <D:lockdiscovery/>
            </D:prop>
            <D:status>HTTP/1.1 200 OK</D:status>
        </D:propstat>
    </D:response>
</D:multistatus>
"""


class TestDavSaxParser(tests.TestCase):

    def _extract_dir_content_from_str(self, str):
        return webdav._extract_dir_content(
            'http://localhost/blah', StringIO(str))

    def _extract_stat_from_str(self, str):
        return webdav._extract_stat_info(
            'http://localhost/blah', StringIO(str))

    def test_unkown_format_response(self):
        # Valid but unrelated xml
        example = """<document/>"""
        self.assertRaises(errors.InvalidHttpResponse,
                          self._extract_dir_content_from_str, example)

    def test_list_dir_malformed_response(self):
        # Invalid xml, neither multistatus nor response are properly closed
        example = """<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:" xmlns:ns0="urn:uuid:c2f41010-65b3-11d1-a29f-00aa00c14882/">
<D:response>
<D:href>http://localhost/</D:href>"""
        self.assertRaises(errors.InvalidHttpResponse,
                          self._extract_dir_content_from_str, example)

    def test_list_dir_incomplete_format_response(self):
        # The information we need is not present
        example = """<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:" xmlns:ns0="urn:uuid:c2f41010-65b3-11d1-a29f-00aa00c14882/">
<D:response>
<D:href>http://localhost/</D:href>
</D:response>
<D:response>
<D:href>http://localhost/titi</D:href>
</D:response>
<D:href>http://localhost/toto</D:href>
</D:multistatus>"""
        self.assertRaises(errors.NotADirectory,
                         self._extract_dir_content_from_str, example)

    def test_list_dir_apache2_example(self):
        example = _get_list_dir_apache2_depth_1_prop()
        self.assertRaises(errors.NotADirectory,
                         self._extract_dir_content_from_str, example)

    def test_list_dir_lighttpd_example(self):
        example = """<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:" xmlns:ns0="urn:uuid:c2f41010-65b3-11d1-a29f-00aa00c14882/">
<D:response>
<D:href>http://localhost/</D:href>
</D:response>
<D:response>
<D:href>http://localhost/titi</D:href>
</D:response>
<D:response>
<D:href>http://localhost/toto</D:href>
</D:response>
</D:multistatus>"""
        self.assertRaises(errors.NotADirectory,
                         self._extract_dir_content_from_str, example)

    def test_list_dir_apache2_dir_depth_1_example(self):
        example = _get_list_dir_apache2_depth_1_allprop()
        self.assertEquals([('executable', False, 14, True),
                           ('read-only', False, 42, False),
                           ('titi', False, 6, False),
                           ('toto', True, -1, False)],
                          self._extract_dir_content_from_str(example))

    def test_stat_malformed_response(self):
        # Invalid xml, neither multistatus nor response are properly closed
        example = """<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:" xmlns:ns0="urn:uuid:c2f41010-65b3-11d1-a29f-00aa00c14882/">
<D:response>
<D:href>http://localhost/</D:href>"""
        self.assertRaises(errors.InvalidHttpResponse,
                          self._extract_stat_from_str, example)

    def test_stat_incomplete_format_response(self):
        # The minimal information is present but doesn't conform to RFC 2518
        # (well, as I understand it since the reference servers disagree on
        # more than details).

        # The href below is not enclosed in a response element and is
        # therefore ignored.
        example = """<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:" xmlns:ns0="urn:uuid:c2f41010-65b3-11d1-a29f-00aa00c14882/">
<D:href>http://localhost/toto</D:href>
</D:multistatus>"""
        self.assertRaises(errors.InvalidHttpResponse,
                          self._extract_stat_from_str, example)

    def test_stat_apache2_file_example(self):
        example = """<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:" xmlns:ns0="DAV:">
<D:response xmlns:lp1="DAV:" xmlns:lp2="http://apache.org/dav/props/">
<D:href>/executable</D:href>
<D:propstat>
<D:prop>
<lp1:resourcetype/>
<lp1:creationdate>2008-06-08T09:50:15Z</lp1:creationdate>
<lp1:getcontentlength>12</lp1:getcontentlength>
<lp1:getlastmodified>Sun, 08 Jun 2008 09:50:11 GMT</lp1:getlastmodified>
<lp1:getetag>"da9f81-0-9ef33ac0"</lp1:getetag>
<lp2:executable>T</lp2:executable>
<D:supportedlock>
<D:lockentry>
<D:lockscope><D:exclusive/></D:lockscope>
<D:locktype><D:write/></D:locktype>
</D:lockentry>
<D:lockentry>
<D:lockscope><D:shared/></D:lockscope>
<D:locktype><D:write/></D:locktype>
</D:lockentry>
</D:supportedlock>
<D:lockdiscovery/>
</D:prop>
<D:status>HTTP/1.1 200 OK</D:status>
</D:propstat>
</D:response>
</D:multistatus>"""
        st = self._extract_stat_from_str(example)
        self.assertEquals(12, st.st_size)
        self.assertFalse(stat.S_ISDIR(st.st_mode))
        self.assertTrue(stat.S_ISREG(st.st_mode))
        self.assertTrue(st.st_mode & stat.S_IXUSR)

    def test_stat_apache2_dir_depth_1_example(self):
        example = _get_list_dir_apache2_depth_1_allprop()
        self.assertRaises(errors.InvalidHttpResponse,
                          self._extract_stat_from_str, example)

    def test_stat_apache2_dir_depth_0_example(self):
        example = """<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:" xmlns:ns0="DAV:">
<D:response xmlns:lp1="DAV:" xmlns:lp2="http://apache.org/dav/props/">
<D:href>/</D:href>
<D:propstat>
<D:prop>
<lp1:resourcetype><D:collection/></lp1:resourcetype>
<lp1:creationdate>2008-06-08T10:50:38Z</lp1:creationdate>
<lp1:getlastmodified>Sun, 08 Jun 2008 10:50:38 GMT</lp1:getlastmodified>
<lp1:getetag>"da7f5a-cc-7722db80"</lp1:getetag>
<D:supportedlock>
<D:lockentry>
<D:lockscope><D:exclusive/></D:lockscope>
<D:locktype><D:write/></D:locktype>
</D:lockentry>
<D:lockentry>
<D:lockscope><D:shared/></D:lockscope>
<D:locktype><D:write/></D:locktype>
</D:lockentry>
</D:supportedlock>
<D:lockdiscovery/>
</D:prop>
<D:status>HTTP/1.1 200 OK</D:status>
</D:propstat>
</D:response>
</D:multistatus>
"""
        st = self._extract_stat_from_str(example)
        self.assertEquals(-1, st.st_size)
        self.assertTrue(stat.S_ISDIR(st.st_mode))
        self.assertTrue(st.st_mode & stat.S_IXUSR)
