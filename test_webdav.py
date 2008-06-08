# Copyright (C) 2006 Canonical Ltd
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

"""Tests for the wedav plugin.

This defines the TestingDAVRequestHandler and the DAVServer classes which
implements the DAV specification parts used by the webdav plugin.
"""

# TODO: Move the server into its own file

# TODO: Implement the testing of the range header for PUT requests (GET request
# are already heavily tested in bzr). Test servers are available there too.

from cStringIO import StringIO
import errno
import httplib
import os
import os.path
import re
import socket
import string
import shutil
import stat
import sys
import time
import urlparse


from bzrlib import (
    errors,
    tests,
    trace,
    )
from bzrlib.tests import (
    http_utils,
    TestUtil,
    )
from bzrlib.tests.http_server import (
    HttpServer,
    TestingHTTPRequestHandler,
    )
from bzrlib.transport.http import _urllib2_wrappers


from bzrlib.plugins.webdav import webdav


class TestingDAVRequestHandler(TestingHTTPRequestHandler):
    """
    Subclass of TestingHTTPRequestHandler handling DAV requests.

    This is not a full implementation of a DAV server, only the parts
    really used by the plugin are.
    """

    _RANGE_HEADER_RE = re.compile(
        r'bytes (?P<begin>\d+)-(?P<end>\d+)/(?P<size>\d+|\*)')


    def _read(self, length):
        """Read the client socket"""
        return self.rfile.read(length)

    def _readline(self):
        """Read a full line on the client socket"""
        return self.rfile.readline()

    def read_body(self):
        """Read the body either by chunk or as a whole."""
        content_length = self.headers.get('Content-Length')
        encoding = self.headers.get('Transfer-Encoding')
        if encoding is not None:
            assert encoding == 'chunked'
            body = []
            # We receive the content by chunk
            while True:
                length, data = self.read_chunk()
                if length == 0:
                    break
                body.append(data)
            body = ''.join(body)

        else:
            if content_length is not None:
                body = self._read(int(content_length))

        return body

    def read_chunk(self):
        """Read a chunk of data.

        A chunk consists of:
        - a line containing the length of the data in hexa,
        - the data.
        - a empty line.

        An empty chunk specifies a length of zero
        """
        length = int(self._readline(),16)
        data = None
        if length != 0:
            data = self._read(length)
            # Eats the newline following the chunk
            self._readline()
        return length, data

    def send_head(self):
        """Specialized version of SimpleHttpServer.

        We *don't* want the apache behavior of permanently redirecting
        directories without trailing slashes to directories with trailing
        slashes. That's a waste and a severe penalty for clients with high
        latency.

        The installation documentation of the plugin should mention the
        DirectorySlash apache directive and insists on turning it *Off*.
        """
        path = self.translate_path(self.path)
        f = None
        if os.path.isdir(path):
            for index in "index.html", "index.htm":
                index = os.path.join(path, index)
                if os.path.exists(index):
                    path = index
                    break
            else:
                return self.list_directory(path)
        ctype = self.guess_type(path)
        if ctype.startswith('text/'):
            mode = 'r'
        else:
            mode = 'rb'
        try:
            f = open(path, mode)
        except IOError:
            self.send_error(404, "File not found")
            return None
        self.send_response(200)
        self.send_header("Content-type", ctype)
        fs = os.fstat(f.fileno())
        self.send_header("Content-Length", str(fs[6]))
        self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
        self.end_headers()
        return f

    def do_PUT(self):
        """Serve a PUT request."""
        # FIXME: test_put_file_unicode makes us emit a traceback because a
        # UnicodeEncodeError occurs after the request headers have been sent be
        # before the body can be send. It's harmless and do not make the test
        # fails. Adressing that will mean protecting all reads from the socket,
        # which is too heavy for now -- vila 20070917
        path = self.translate_path(self.path)
        trace.mutter("do_PUT rel: [%s], abs: [%s]" % (self.path,path))

        do_append = False
        # Check the Content-Range header
        range_header = self.headers.get('Content-Range')
        if range_header is not None:
            match = self._RANGE_HEADER_RE.match(range_header)
            if match is None:
                # FIXME: RFC2616 says to return a 501 if we don't
                # understand the Content-Range header, but Apache
                # just ignores them (bad Apache).
                self.send_error(501, 'Not Implemented')
                return
            begin = int(match.group('begin'))
            do_append = True

        if self.headers.get('Expect') == '100-continue':
            # Tell the client to go ahead, we're ready to get the content
            self.send_response(100,"Continue")
            self.end_headers()

        try:
            trace.mutter("do_PUT will try to open: [%s]" % path)
            # Always write in binary mode.
            if do_append:
                f = open(path,'ab')
                f.seek(begin)
            else:
                f = open(path, 'wb')
        except (IOError, OSError), e :
            self.send_error(409, 'Conflict')
            return

        try:
            data = self.read_body()
            f.write(data)
        except (IOError, OSError):
            # FIXME: We leave a partially written file here
            self.send_error(409, "Conflict")
            f.close()
            return
        f.close()
        trace.mutter("do_PUT done: [%s]" % self.path)
        self.send_response(201)
        self.end_headers()

    def do_MKCOL(self):
        """
        Serve a MKCOL request.

        MKCOL is an mkdir in DAV terminology for our part.
        """
        path = self.translate_path(self.path)
        trace.mutter("do_MKCOL rel: [%s], abs: [%s]" % (self.path,path))
        try:
            os.mkdir(path)
        except (IOError, OSError),e:
            if e.errno in (errno.ENOENT, ):
                self.send_error(409, "Conflict")
            elif e.errno in (errno.EEXIST, errno.ENOTDIR):
                self.send_error(405, "Not allowed")
            else:
                # Ok we fail for an unnkown reason :-/
                raise
        else:
            self.send_response(201)
            self.end_headers()

    def do_COPY(self):
        """Serve a COPY request."""

        url_to = self.headers.get('Destination')
        if url_to is None:
            self.send_error(400,"Destination header missing")
            return
        (scheme, netloc, rel_to,
         params, query, fragment) = urlparse.urlparse(url_to)
        trace.mutter("urlparse: (%s) [%s]" % (url_to, rel_to))
        trace.mutter("do_COPY rel_from: [%s], rel_to: [%s]" % (self.path,
                                                               rel_to))
        abs_from = self.translate_path(self.path)
        abs_to = self.translate_path(rel_to)
        try:
            # TODO:  Check that rel_from  exists and  rel_to does
            # not.  In the  mean  time, just  go  along and  trap
            # exceptions
            shutil.copyfile(abs_from,abs_to)
        except (IOError, OSError), e:
            if e.errno == errno.ENOENT:
                self.send_error(404,"File not found") ;
            else:
                self.send_error(409,"Conflict") ;
        else:
            # TODO: We may be able  to return 204 "No content" if
            # rel_to was existing (even  if the "No content" part
            # seems misleading, RFC2518 says so, stop arguing :)
            self.send_response(201)
            self.end_headers()

    def do_DELETE(self):
        """Serve a DELETE request.

        We don't implement a true DELETE as DAV defines it
        because we *should* fail to delete a non empty dir.
        """
        path = self.translate_path(self.path)
        trace.mutter("do_DELETE rel: [%s], abs: [%s]" % (self.path, path))
        try:
            # DAV  makes no  distinction between  files  and dirs
            # when required to nuke them,  but we have to. And we
            # also watch out for symlinks.
            real_path = os.path.realpath(path)
            if os.path.isdir(real_path):
                os.rmdir(path)
            else:
                os.remove(path)
        except (IOError, OSError),e:
            if e.errno in (errno.ENOENT, ):
                self.send_error(404, "File not found")
            elif e.errno in (errno.ENOTEMPTY, ):
                # FIXME: Really gray area, we are not supposed to
                # fail  here :-/ If  we act  as a  conforming DAV
                # server we should  delete the directory content,
                # but bzr may want to  test that we don't. So, as
                # we want to conform to bzr, we don't.
                self.send_error(999, "Directory not empty")
            else:
                # Ok we fail for an unnkown reason :-/
                raise
        else:
            self.send_response(204) # Default success code
            self.end_headers()

    def do_MOVE(self):
        """Serve a MOVE request."""

        url_to = self.headers.get('Destination')
        if url_to is None:
            self.send_error(400,"Destination header missing")
            return
        overwrite_header = self.headers.get('Overwrite')
        if overwrite_header == 'F':
            should_overwrite = False
        else:
            should_overwrite = True
        (scheme, netloc, rel_to,
         params, query, fragment) = urlparse.urlparse(url_to)
        trace.mutter("urlparse: (%s) [%s]" % (url_to, rel_to))
        trace.mutter("do_MOVE rel_from: [%s], rel_to: [%s]" % (self.path,
                                                               rel_to))
        abs_from = self.translate_path(self.path)
        abs_to = self.translate_path(rel_to)
        if should_overwrite is False and os.access(abs_to, os.F_OK):
            self.send_error(412,"Precondition Failed")
            return
        try:
            os.rename(abs_from, abs_to)
        except (IOError, OSError), e:
            if e.errno == errno.ENOENT:
                self.send_error(404,"File not found") ;
            else:
                self.send_error(409,"Conflict") ;
        else:
            # TODO: We may be able  to return 204 "No content" if
            # rel_to was existing (even  if the "No content" part
            # seems misleading, RFC2518 says so, stop arguing :)
            self.send_response(201)
            self.end_headers()

class TestingDAVAppendRequestHandler(TestingDAVRequestHandler):
    """
    Subclass of TestingDAVRequestHandler implementing te APPEND command.

    http://www.ietf.org/internet-drafts/draft-suma-append-patch-00.txt
    propose two new commands: APPEND and PATCH. Their description
    is sparse, this is a best effort attempt to implement the
    APPEND command.
    """
    def do_APPEND(self):
        """Serve an APPEND request"""
        path = self.translate_path(self.path)
        trace.mutter("do_APPEND rel: [%s], abs: [%s]" % (self.path,path))

        if self.headers.get('Expect') == '100-continue':
            # Tell the client to go ahead, we're ready to get the content
            self.send_response(100,"Continue")
            self.end_headers()

        try:
            # Always write in binary mode.
            trace.mutter("do_APPEND will try to open: [%s]" % path)
            f = open(path, 'wb+')
        except (IOError, OSError), e :
            self.send_error(409, "Conflict")
            return

        try:
            data = self.read_body()
            f.write(data)
        except (IOError, OSError):
            # FIXME: We leave a partially updated file here
            self.send_error(409, "Conflict")
            f.close()
            return
        f.close()
        trace.mutter("do_APPEND done: [%s]" % self.path)
        # FIXME: We should send 204 if the file didn't exist before
        self.send_response(201)
        self.end_headers()


class DAVServer(HttpServer):
    """Subclass of HttpServer that gives http+webdav urls.

    This is for use in testing: connections to this server will always go
    through _urllib where possible.
    """

    def __init__(self):
        # We    have   special    requests    to   handle    that
        # HttpServer_urllib doesn't know about
        super(DAVServer,self).__init__(TestingDAVRequestHandler)

    # urls returned by this server should require the webdav client impl
    _url_protocol = 'http+webdav'


class DAVServer_append(DAVServer):
    """Subclass of HttpServer that gives http+webdav urls.

    This is for use in testing: connections to this server will always go
    through pycurl where possible.
    This server implements the proposed
    (www.ietf.org/internet-drafts/draft-suma-append-patch-00.txt)
    APPEND request.
    """

    def __init__(self):
        # We    have   special    requests    to   handle    that
        # HttpServer_PyCurl don't know about
        super(DAVServer_append,self).__init__(TestingDAVAppendRequestHandler)

    # urls returned by this server should require the webdav client impl
    _url_protocol = 'http+webdav'


class TestCaseWithDAVServer(tests.TestCaseWithTransport):
    """A support class that provides urls that are http+webdav://.

    This is done by forcing the server to be an http DAV one.
    """
    def setUp(self):
        super(TestCaseWithDAVServer, self).setUp()
        self.transport_server = DAVServer

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
                <lp1:getcontentlength>0</lp1:getcontentlength>
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
                <lp1:getcontentlength>0</lp1:getcontentlength>
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
        # The minimal information is present but doesn't conform to RFC 2518
        # (well, as I understand it since the reference servers disagree on
        # more than details).

        # The last href below is not enclosed in a response element and is
        # therefore ignored.
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
        self.assertEqual(['titi'], self._extract_dir_content_from_str(example))

    def test_list_dir_apache2_example(self):
        example = _get_list_dir_apache2_depth_1_prop()
        self.assertEqual(['a', 'b', 'c'],
                         self._extract_dir_content_from_str(example))

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
        self.assertEqual(['titi', 'toto'],
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
        self.assertEquals(None, st.st_size)
        self.assertTrue(stat.S_ISDIR(st.st_mode))
        self.assertTrue(st.st_mode & stat.S_IXUSR)
