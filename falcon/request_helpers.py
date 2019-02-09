# Copyright 2013 by Rackspace Hosting, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Utilities for the Request class."""

import io
import re

from falcon.util.structures import ETag


_ETAG_PATTERN = re.compile(r'([Ww]/)?(?:"(.*?)"|(.*?))(?:\s*,\s*|$)')


def header_property(wsgi_name):
    """Create a read-only header property.

    Args:
        wsgi_name (str): Case-sensitive name of the header as it would
            appear in the WSGI environ ``dict`` (i.e., 'HTTP_*')

    Returns:
        A property instance than can be assigned to a class variable.

    """

    def fget(self):
        try:
            return self.env[wsgi_name] or None
        except KeyError:
            return None

    return property(fget)


def make_etag(value, is_weak=False):
    """Creates and returns a ETag object."""
    etag = ETag(value)
    etag.is_weak = is_weak
    return etag


def parse_etags(etag_str):
    """
    Parse a string of ETags given in the If-Match or If-None-Match header as
    defined by RFC 7232.

    Args:
        etag_str (str): An ASCII header value to parse ETags from. ETag values
            within may be prefixed by ``W/`` to indicate that the weak comparison
            function should be used.

    Returns:
        A list of unquoted ETags or ``['*']`` if all ETags should be matched.

    """
    etags = []

    if etag_str is None:
        return etags

    etag_str = etag_str.strip()
    if not etag_str:
        return etags

    if etag_str == '*':
        etags.append(etag_str)
        return etags

    if ',' not in etag_str:
        value = etag_str
        is_weak = False
        if value.startswith(('W/', 'w/')):
            is_weak = True
            value = value[2:]
        if value[:1] == value[-1:] == '"':
            value = value[1:-1]
        etags.append(make_etag(value, is_weak))
    else:
        pos = 0
        end = len(etag_str)
        while pos < end:
            match = _ETAG_PATTERN.match(etag_str, pos)
            if match is None:
                break
            is_weak, quoted, raw = match.groups()
            value = quoted or raw
            if value:
                etags.append(make_etag(value, bool(is_weak)))
            pos = match.end()

    return etags


class BoundedStream(io.IOBase):
    """Wrap *wsgi.input* streams to make them more robust.

    ``socket._fileobject`` and ``io.BufferedReader`` are sometimes used
    to implement *wsgi.input*. However, app developers are often burned
    by the fact that the `read()` method for these objects block
    indefinitely if either no size is passed, or a size greater than
    the request's content length is passed to the method.

    This class normalizes *wsgi.input* behavior between WSGI servers
    by implementing non-blocking behavior for the cases mentioned
    above.

    Args:
        stream: Instance of ``socket._fileobject`` from
            ``environ['wsgi.input']``
        stream_len: Expected content length of the stream.

    """

    def __init__(self, stream, stream_len):
        self.stream = stream
        self.stream_len = stream_len

        self._bytes_remaining = self.stream_len

    def __iter__(self):
        return self

    def __next__(self):
        return next(self.stream)

    next = __next__

    def _read(self, size, target):
        """Helper function for proxing reads to the underlying stream.

        Args:
            size (int): Maximum number of bytes to read. Will be
                coerced, if None or -1, to the number of remaining bytes
                in the stream. Will likewise be coerced if greater than
                the number of remaining bytes, to avoid making a
                blocking call to the wrapped stream.
            target (callable): Once `size` has been fixed up, this function
                will be called to actually do the work.

        Returns:
            bytes: Data read from the stream, as returned by `target`.

        """

        # NOTE(kgriffs): Default to reading all remaining bytes if the
        # size is not specified or is out of bounds. This behaves
        # similarly to the IO streams passed in by non-wsgiref servers.
        if (size is None or size == -1 or size > self._bytes_remaining):
            size = self._bytes_remaining

        self._bytes_remaining -= size
        return target(size)

    def readable(self):
        """Always returns ``True``."""
        return True

    def seekable(self):
        """Always returns ``False``."""
        return False

    def writeable(self):
        """Always returns ``False``."""
        return False

    def read(self, size=None):
        """Read from the stream.

        Args:
            size (int): Maximum number of bytes/characters to read.
                Defaults to reading until EOF.

        Returns:
            bytes: Data read from the stream.

        """

        return self._read(size, self.stream.read)

    def readline(self, limit=None):
        """Read a line from the stream.

        Args:
            limit (int): Maximum number of bytes/characters to read.
                Defaults to reading until EOF.

        Returns:
            bytes: Data read from the stream.

        """

        return self._read(limit, self.stream.readline)

    def readlines(self, hint=None):
        """Read lines from the stream.

        Args:
            hint (int): Maximum number of bytes/characters to read.
                Defaults to reading until EOF.

        Returns:
            bytes: Data read from the stream.

        """

        return self._read(hint, self.stream.readlines)

    def write(self, data):
        """Always raises IOError; writing is not supported."""

        raise IOError('Stream is not writeable')

    def exhaust(self, chunk_size=64 * 1024):
        """Exhaust the stream.

        This consumes all the data left until the limit is reached.

        Args:
            chunk_size (int): The size for a chunk (default: 64 KB).
                It will read the chunk until the stream is exhausted.
        """
        while True:
            chunk = self.read(chunk_size)
            if not chunk:
                break

    @property
    def is_exhausted(self):
        """If the stream is exhausted this attribute is ``True``."""
        return self._bytes_remaining <= 0


# NOTE(kgriffs): Alias for backwards-compat
Body = BoundedStream
