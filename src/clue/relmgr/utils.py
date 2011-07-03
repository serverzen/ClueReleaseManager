from __future__ import with_statement

import logging
import os
import pkg_resources
import werkzeug
from werkzeug import routing
import urllib2

logger = logging.getLogger('clue.relmgr[main     ]')
logger.setLevel(level=logging.INFO)

werklogger = logging.getLogger('clue.relmgr[werkzeug ]')
werklogger.setLevel(level=logging.INFO)

securelogger = logging.getLogger('clue.relmgr[security ]')
securelogger.setLevel(level=logging.INFO)

accesslogger = logging.getLogger('clue.relmgr[access   ]')
accesslogger.setLevel(level=logging.INFO)


class respond(object):

    def __init__(self, func, content_type='text/html; charset=UTF-8'):
        self.func = func
        self.content_type = content_type

    def __get__(self, obj, *args, **kwargs):

        def newfunc(*args, **kwargs):
            r = werkzeug.Response(content_type=self.content_type)
            r.response = self.func(obj, *args, **kwargs)
            return r
        return newfunc


def pop_path(environ=None, req=None):
    if req is not None:
        environ = req.environ
    path = environ.get('PATH_INFO', '')
    if not path:
        path = '/'
    path = path.split('/')[1:]

    if len(path) > 0:
        script_name = environ.get('SCRIPT_NAME', '/')
        if not script_name.endswith('/'):
            script_name += '/'
        script_name += path[0] + '/'

        environ['SCRIPT_NAME'] = script_name
        environ['PATH_INFO'] = '/' + '/'.join(path[1:])
        if req is not None:
            if hasattr(req, 'path'):
                del req.path
            if hasattr(req, 'url'):
                del req.url
            if hasattr(req, 'url_root'):
                del req.url_root
        return path[0]
    return None


def update_obj(obj, **kwargs):
    """Set all of the attributes on an object.

      >>> class Mock(object):
      ...     pass
      >>> mock = Mock()
      >>> update_obj(mock, foo=1, bar=2)
      >>> sorted(mock.__dict__.items())
      [('bar', 2), ('foo', 1)]
    """

    for k, v in kwargs.items():
        setattr(obj, k, v)


def make_distro_id(name):
    """Deduce a distro_id from the given name.

      >>> make_distro_id('Foo Bar  Cool')
      'foo-bar-cool'
    """

    distro_id = ''
    for x in name.lower():
        if x in ' =':
            if not distro_id.endswith('-'):
                distro_id += '-'
            continue

        distro_id += x

    return distro_id


class AbstractContent(object):

    def setup_stream(self):
        raise NotImplementedError()

    def save(self, dest):
        opened = self.setup_stream()

        with open(dest, 'wb') as f:
            bufsize = 1024
            data = opened.read(bufsize)
            f.write(data)
            while len(data) == bufsize:
                data = opened.read(bufsize)
                if len(data) > 0:
                    f.write(data)

        opened.close()


def get_content(v):
    if v.startswith('http:') or v.startswith('https:'):
        return UrlContent(v)
    return FileContent(v)


class FileContent(AbstractContent):

    def __init__(self, path, filename=None):
        self.path = path
        self.filename = filename or os.path.basename(path)

    def setup_stream(self):
        return open(self.filename, 'rb')


class UrlContent(AbstractContent):

    def __init__(self, url, filename=None):
        self.url = url
        self.filename = filename or os.path.basename(url)
        self._stream = None

    def setup_stream(self):
        return urllib2.urlopen(self.url)


class Subset(object):

    def __init__(self, all, first, max):
        self.all = all
        self.first = first
        self.max = max

    @property
    def full_item_count(self):
        return len(self.all)

    @property
    def results(self):
        return self.all[self.first:self.first+self.max]

    def __iter__(self):
        return iter(self.results)


class Page(Subset):

    def __init__(self, all, page_num, per_page):
        self.all = all
        self.page_num = page_num
        self.max = per_page

    @property
    def total_pages(self):
        return (self.full_item_count - 1) / self.max + 1

    @property
    def first(self):
        return (self.page_num-1) * self.max


class QueryPage(Page):

    def __init__(self, query, page_num, per_page):
        self.query = query
        self.page_num = page_num
        self.per_page = per_page

    @property
    def full_item_count(self):
        return self.query.count()

    @property
    def results(self):
        query = self.query.offset(self.first)
        return query.limit(self.per_page)


def parse_distro_from_filename(filename):
    f = os.path.basename(filename)
    if '#' in f:
        f, ignore = f.split('#', 1)
    for x in ('.tar.gz', '.tar.bz2', '.zip', '.tar', '.egg'):
        if f.endswith(x):
            f = f[:-1*len(x)]
            break
    name, ver = f.split('-', 1)
    return name, ver


def pkg_info_as_distro(metadata):

    def desc(d, v):
        lines = v.split('\n')
        changed = v
        if len(lines) > 1:
            indent = len(lines[1]) - len(lines[1].lstrip())
            if indent > 0:
                changed = lines[0] + '\n'
                for x in lines[1:]:
                    changed = changed + x[indent:] + '\n'
        d['description'] = changed

    mapping = {
        'Name': 'name',
        'Author': 'author',
        'Author-email': 'author_email',
        'License': 'license',
        'Description': desc,
        'Summary': 'summary',
        'Classifier': 'classifier',
        'Keywords': 'keywords',
        }

    md = {}
    for x, y in mapping.items():
        if x in metadata:
            if callable(y):
                y(md, metadata[x])
            else:
                md[y] = metadata[x]
    return md


ARCHIVE_EXTS = ['.tar.bz2', '.tar.gz', '.zip', '.egg', '.tar']


def get_archive_split(f):
    basename = os.path.basename(f)
    ext = ''
    for x in ARCHIVE_EXTS:
        if basename.endswith(x):
            basename = basename[:basename.find(x)]
            ext = x
            break

    return basename, ext


def parse_version(f):
    basename, ext = get_archive_split(f)
    match = pkg_resources.EGG_NAME(basename)
    if match:
        project_name, version, py_version, platform = match.group(
            'name', 'ver', 'pyver', 'plat')
        return version
    return None


REQ_OPTS = ['>=', '<=', '==', '=']


def parse_req_parts(s):
    for x in REQ_OPTS:
        pos = s.find(x)
        if pos > -1:
            return (s[:pos], s[pos:pos+len(x)], s[pos+len(x):])
    return (None, None, None)


NO_CACHE_HEADERS = (
    ('Expires', 'Sat, 1 Jan 2000 05:00:00 GMT'),
    ('Cache-Control', 'no-store, no-cache, must-revalidate'),
    ('Cache-Control', 'post-check=0, pre-check=0'),
    ('Pragma', 'no-cache'),
    )


class NonCachedRedirect(routing.RequestRedirect):

    def get_response(self, environ):
        res = super(NonCachedRedirect, self).get_response(environ)
        for x, y in NO_CACHE_HEADERS:
            res.headers[x] = y
        return res


class CommonError(Exception):
    pass
