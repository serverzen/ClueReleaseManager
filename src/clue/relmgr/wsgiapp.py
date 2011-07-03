from __future__ import with_statement
import os
import re
import xmlrpclib
import ConfigParser
import htpasswd

import werkzeug
from werkzeug import exceptions as werkexc
from repoze.who import (middleware as whomiddleware,
                        config as repozewhoconfig, classifiers)
from repoze.who.plugins import (basicauth,
                                htpasswd as repozehtpasswd,
                                sql)
from werkzeug import routing
import jinja2
from docutils import core as docutilscore

from clue.relmgr import utils, pypi, restmodel, model
import cluedojo.wsgiapp as dojowsgi
from clue.secure import wsgiapp as securewsgi
from clue.secure import htpasswd as securehtpasswd
from clue.secure import groupfile

import pkg_resources

__version__ = pkg_resources.get_distribution('ClueReleaseManager').version

APP_JSON_MIME_TYPE = 'application/json'


def format_datetime(dt, show_time=True):
    if dt is None:
        return 'N/A'

    dateformat = '%b-%d-%Y'
    timeformat = '%I:%M%p'
    dtformat = dateformat + ' ' + timeformat

    if hasattr(dt, 'hour') and hasattr(dt, 'year') and show_time:
        return dt.strftime(dtformat)
    if hasattr(dt, 'hour') and show_time:
        return dt.strftime(timeformat)
    if hasattr(dt, 'year'):
        return dt.strftime(dateformat)

    return 'N/A'


class TemplateLoader(object):

    can_manage_security = False

    def __init__(self, use_dojo, debug=False):
        self.template_loader = jinja2.Environment(
            loader=jinja2.PackageLoader('clue.relmgr', 'templates'))
        self.template_loader.globals.update(dict(
            use_dojo = use_dojo,
            format_datetime = format_datetime))
        self.debug = debug

    def get_template(self, name, environ):
        req = werkzeug.Request(environ)
        tmpl = self.template_loader.get_template(name)
        tmpl.globals['url_root'] = url_root = req.url_root
        tmpl.globals['debug'] = debug = self.debug
        tmpl.globals['can_manage_security'] = self.can_manage_security

        if debug:
            root = req.url_root
            if root.endswith('/d/'):
                root = root[:-3]
            if root.endswith('/'):
                root = root[:-1]
            root = root[len(req.host_url):]
            dojo_root = root + '/dojo'
            tmpl.globals['dojo_block'] = '''
<script type="text/javascript">
    djConfig = {
        isDebug: %(debug)s,
        debugAtAllCosts: %(debug)s,
        useXDomain: false,
        modulePaths: {
            'clue.relmgr': '%(root)s/static/clue/relmgr',
            'clue.secure': '%(root)s/secure/static/clue/secure'
        }
    };
</script>

<script type="text/javascript" src="%(dojo_root)s/dojo/dojo.js"></script>
<link rel="stylesheet" href="%(dojo_root)s/dijit/themes/tundra/tundra.css">
<link rel="stylesheet" href="%(root)s/secure/static/mgt.css">
''' % {'dojo_root': dojo_root, 'root': root, 'debug': str(debug).lower()}

        else:
            tmpl.globals['dojo_block'] = '''
<script type="text/javascript">
    djConfig = {
        baseUrl: '%(url_root)s',
        isDebug: %(debug)s,
        debugAtAllCosts: %(debug)s,
        modulePaths: {
            'clue.relmgr': 'static/clue/relmgr',
            'clue.secure': 'secure/static/clue/secure'
        }
    };
</script>
''' % {'debug': str(debug).lower(), 'url_root': url_root}
            tmpl.globals['dojo_block'] += dojowsgi.get_google_block(environ)


        return tmpl


class HTTPNoSuchDistroError(werkexc.NotFound, model.NoSuchDistroError):

    def __init__(self, distro_id):
        super(model.NoSuchDistroError, self).__init__(distro_id)


class RegexRule(routing.Rule):
    """A raw regex-based routing rule.

      >>> r = RegexRule('/foo', 'bar')
      >>> r.match('abc')
      >>> r.match('/foo')
      ('bar',)
      >>> r.bind(None)
    """

    def __init__(self, string, endpoint):
        super(RegexRule, self).__init__(string, endpoint=endpoint)
        self._regex = re.compile(string)

    def match(self, path):
        r = self._regex.search(path)
        if r:
            return (self.endpoint, )
        return None


class AbstractPyPiApp(object):
    """An app that uses a pypi instance.

      >>> a = AbstractPyPiApp(None)
      >>> holder = []
      >>> def start(status, y, holder=holder):
      ...     holder[:] = [status, y]
      >>> environ = {'SERVER_NAME': 'foo.com', 'wsgi.url_scheme': 'http',
      ...            'SERVER_PORT': '8080', 'REQUEST_METHOD': 'GET'}
      >>> r = a(environ, start)
      Traceback (most recent call last):
      NotImplementedError: Please provide urlmap

      >>> a.urlmap = routing.Map()
      >>> r = a(environ, start)
      >>> holder[0]
      '404 NOT FOUND'
    """

    logger = utils.logger
    urlmap = None

    def __init__(self, pypi, debug=False):
        self.pypi = pypi
        self.debug = debug
        self.templates = TemplateLoader(use_dojo=True,
                                        debug=debug)

    def __call__(self, environ, start_response):
        if self.urlmap is None:
            raise NotImplementedError('Please provide urlmap')

        urls = self.urlmap.bind_to_environ(environ)
        res = None
        try:
            endpoint, kwargs = urls.match()

            res = getattr(self, 'subapp_'+endpoint, None)
            if res is not None:
                utils.pop_path(environ)
                return res(environ, start_response)

            res = getattr(self, 'app_'+endpoint, None)
            if res is not None:
                return res(environ, start_response)

            attr = getattr(self, 'respond_'+endpoint, None)
            if attr is not None:
                res = attr(werkzeug.Request(environ), **kwargs)
                return res(environ, start_response)

        except werkexc.NotFound, exc:
            tmpl = self.templates.get_template('404.html', environ)
            req = werkzeug.Request(environ)
            res = werkzeug.Response(tmpl.render(exc=exc,
                                                version=__version__),
                                    content_type='text/html; charset=UTF-8',
                                    status=404)
            return res(environ, start_response)
        except werkexc.HTTPException, exc:
            return exc(environ, start_response)

        res = werkzeug.Response(werkzeug.Request(environ).path, status=404)
        return res(environ, start_response)

    def globs(self, environ, **extra):
        req = werkzeug.Request(environ)
        all = {'url_root': req.url_root}
        if environ.get('REMOTE_USER', False):
            all['remote_user'] = environ['REMOTE_USER']

        all.update(extra)
        return all


class SimpleIndexApp(AbstractPyPiApp):
    """Represents one index in the pypi server.

      >>> from clue.relmgr.pypi import SimplePyPi
      >>> s = SimpleIndexApp(SimplePyPi())
      >>> [x for x in s.respond_index(None).response]
      [u'<html><body><ul>', u'</ul></body></html>']
    """

    urlmap = routing.Map()
    urlmap.add(routing.Rule('/', endpoint='index'))
    urlmap.add(routing.Rule('/<distro_id>/', endpoint='distro'))

    def __init__(self, pypi, backup_pypis=[], debug=False):
        super(SimpleIndexApp, self).__init__(pypi, debug)
        self.backup_pypis = backup_pypis

    @utils.respond
    def respond_index(self, req):
        yield u'<html><body><ul>'

        for distro in self.pypi.get_distros():
            yield u'<li><a href="%s/">%s</a></li>' % (distro.distro_id,
                                                      distro.name)
        yield u'</ul></body></html>'

    @utils.respond
    def respond_distro(self, req, distro_id):
        yield u'<html><body><ul>\n'

        distro_id = utils.make_distro_id(distro_id)

        distro = self.pypi.get_distro(distro_id)
        if distro is None and self.backup_pypis:
            if not try_to_update(self.pypi, distro_id, self.backup_pypis):
                raise HTTPNoSuchDistroError(distro_id)

        for fname in self.pypi.get_files(distro_id):
            base = os.path.basename(fname)
            url = '../../d/'+distro_id+'/f/'+base
            yield u'<li><a href="%s">%s</a></li>\n' % (url, base)

        yield u'</ul></body></html>'


def _get_remote_info(pypi, distro_id, pypi_url):
    server = xmlrpclib.Server(pypi_url)
    res = server.search({'name': distro_id})
    match = None
    for x in res:
        if utils.make_distro_id(x['name']) == utils.make_distro_id(distro_id):
            match = x
            break

    if not match:
        return None

    data = {}
    name = match['name']
    urls = []
    for rel in server.package_releases(name):
        data = server.release_data(name, rel)
        urls += [(rel, x) for x in server.release_urls(name, rel)]

    kwargs = dict(data)
    if kwargs.get('classifiers'):
        kwargs['classifiers'] = \
            u'\n'.join(kwargs['classifiers'])

    return (name, kwargs, urls)


def try_to_update(pypi, distro_id, backup_pypis):
    for pypi_url in backup_pypis:
        info = _get_remote_info(pypi, distro_id, pypi_url)
        if info:
            name, kwargs, urls = info

            pypi.update_metadata(**kwargs)

            for rel, urldict in urls:
                content = utils.UrlContent(urldict['url'], urldict['filename'])
                pypi.upload_files(name, content)

            return True

    return False

def protect(function):
    def _protect(self,req):
        remote_user = req.environ.get('REMOTE_USER', None)
        if not remote_user:
            raise werkexc.Unauthorized
        return function(self, req)
    return _protect    

class PyPiInnerApp(AbstractPyPiApp):
    """WSGI app for serving up pypi functionality.
    """

    urlmap = routing.Map()
    urlmap.add(routing.Rule('/', methods=['POST'], endpoint='pypi_action'))
    urlmap.add(routing.Rule('/', methods=['GET'], endpoint='root'))
    urlmap.add(routing.Rule('/login', endpoint='login'))
    urlmap.add(routing.Rule('/logout', endpoint='logout'))
    urlmap.add(routing.Rule('/users', endpoint='users'))
    urlmap.add(routing.Rule('/adduser', endpoint='adduser'))
    urlmap.add(routing.Rule('/updateroles', endpoint='update_roles'))
    urlmap.add(routing.Rule('/simple', redirect_to='simple/'))
    urlmap.add(routing.Rule('/simple/', endpoint='simple'))
    urlmap.add(RegexRule('/simple/.*', endpoint='simple'))
    urlmap.add(routing.Rule('/favicon.ico', endpoint='special_static'))
    urlmap.add(routing.Rule('/d/', endpoint='distro'))
    urlmap.add(routing.Rule('/d/<string:distro_id>/', endpoint='distro'))
    urlmap.add(routing.Rule('/d/<string:distro_id>/f/', endpoint='file'))
    urlmap.add(routing.Rule('/d/<string:distro_id>/f/<filename>',
                            endpoint='file'))
    urlmap.add(routing.Rule('/d/<string:distro_id>/i/',
                            endpoint='customindex'))
    urlmap.add(routing.Rule('/d/<string:distro_id>/i/<indexname>',
                            endpoint='customindex'))
    urlmap.add(routing.Rule('/d/<string:distro_id>/i/<indexname>/',
                            endpoint='customindex'))
    urlmap.add(routing.Rule('/<string:distro_id>/',
                            endpoint='redirect_distro'))
    urlmap.add(routing.Rule('/search', endpoint='search'))

    def __init__(self, pypi, backup_pypis=[], debug=False):
        super(PyPiInnerApp, self).__init__(pypi, debug)
        self.subapp_simple = SimpleIndexApp(pypi, backup_pypis, debug)
        self.backup_pypis = backup_pypis
        self.restishapp = restmodel.app_factory(self.pypi, debug)

    def app_special_static(self, environ, start_response):
        env = dict(environ)
        env['PATH_INFO'] = '/static' + env['PATH_INFO']
        return self.top(env, start_response)

    def respond_redirect_distro(self, req, distro_id):
        url = req.url_root
        if not url.endswith('/'):
            url += '/'
        if 'text/html' not in req.headers.get('Accept', '').split(','):
            # try to catch setuptools
            url += 'simple/'
        else:
            url += 'd/'
        url += distro_id + '/'
        raise routing.RequestRedirect(url)

    def subapp_file(self, environ, start_response):
        req = werkzeug.Request(environ)
        if req.accept_mimetypes.best == APP_JSON_MIME_TYPE:
            return self.restishapp(environ, start_response)

        segments = [x for x in req.path.split('/') if x]
        distro_id = None
        filename = None
        if len(segments) > 0:
            distro_id = segments[0]
        if len(segments) > 2:
            filename = segments[2]

        res = werkzeug.Response()
        res.content_type = 'application/octet-stream'
        res.response = open(self.pypi.get_file(distro_id,
                                               filename), 'rb')
        return res(environ, start_response)

    def subapp_customindex(self, environ, start_response):
        req = werkzeug.Request(environ)
        if req.accept_mimetypes.best == APP_JSON_MIME_TYPE:
            return self.restishapp(environ, start_response)

        segments = [x for x in req.path.split('/') if x]
        distro_id = None
        filename = None
        if len(segments) > 0:
            distro_id = segments[0]
        if len(segments) > 2:
            indexname = segments[2]

        index = self.pypi.get_index(distro_id, indexname)

        content = []
        content.append(u'<html><body><ul>')

        for distro, pkgdistro, fname in index:
            if isinstance(distro, (str, unicode)):
                content.append(u'<li>%s (no such distro)</li>' % distro)
            else:
                content.append(u'<li><a href="../../%s/f/%s">%s</a></li>'
                               % (distro.distro_id, fname, fname))
        content.append(u'</ul></body></html>')
        res = werkzeug.Response()
        res.content_type = 'text/html'
        res.response = u'\n'.join(content)
        return res(environ, start_response)

    @utils.respond
    def respond_root(self, req, distro_id=None):
        tmpl = self.templates.get_template('browser.html', req.environ)
        latest = self.pypi.get_distros('last_updated desc')
        page_num = int(req.args.get('page_num', 1))
        page = utils.Page(latest, page_num, 20)
        yield tmpl.render(page=page,
                          title='Latest Updates',
                          version=__version__,
                          **self.globs(req.environ))

    @utils.respond
    def respond_search(self, req):
        s = req.values.get('s', '')
        tmpl = self.templates.get_template('browser.html', req.environ)
        results = self.pypi.search(s)
        page_num = int(req.args.get('page_num', 1))
        page = utils.Page(results, page_num, 20)
        yield tmpl.render(s=s,
                          title='Search Results for "%s"' % s,
                          page=page,
                          version=__version__,
                          **self.globs(req.environ))

    def subapp_distro(self, environ, start_response):
        req = werkzeug.Request(environ)
        if req.accept_mimetypes.best == APP_JSON_MIME_TYPE:
            return self.restishapp(environ, start_response)

        segments = [x for x in req.path.split('/') if x]
        distro_id = None
        if len(segments) > 0:
            distro_id = segments[0]

        if distro_id is None:
            raise routing.RequestRedirect(req.url_root)

        try:
            distro = self.pypi.get_distro(distro_id)
        except pypi.SecurityError, exc:
            tmpl = self.templates.get_template('403.html', environ)
            req = werkzeug.Request(environ)
            url_root = req.url_root[:-2]
            extra_message = 'Cannot access "%s"' % distro_id
            res = werkzeug.Response(tmpl.render(exc=exc,
                                                extra_message=extra_message,
                                                url_root=url_root,
                                                version=__version__),
                                    content_type='text/html; charset=UTF-8',
                                    status=403)
            return res(environ, start_response)

        if distro is None:
            if self.backup_pypis:
                if not try_to_update(self.pypi, distro_id, self.backup_pypis):
                    raise HTTPNoSuchDistroError(distro_id)
            else:
                raise HTTPNoSuchDistroError(distro_id)

        tmpl = self.templates.get_template('distro.html', environ)
        url_root = '/'.join(req.url_root.split('/')[:-2]) + '/'

        indexes = []
        for x in self.pypi.get_indexes(distro_id):
            indexes.append({'indexname': x,
                            'url': 'i/'+x})

        files = self.pypi.get_files(distro_id)

        distro = self.pypi.get_distro(distro_id)
        if distro.classifiers is not None:
            c = [x.strip().split('::')[-1].strip()
                 for x in distro.classifiers.split('\n')]
        else:
            c = []

        extra_css_classes = []
        if self.pypi.has_role(distro_id,
                              pypi.MANAGER_ROLE,
                              model.OWNER_ROLE):
            extra_css_classes.append('can-modify')
        kwargs = self.globs(req.environ,
                            distro=distro,
                            distro_extra={'classifiers': c},
                            distro_url=req.url,
                            indexes=indexes,
                            extra_css_classes=' '.join(extra_css_classes),
                            files=[
                                {'filename': os.path.basename(x),
                                 'url': '%sd/%s/f/%s' % (url_root,
                                                         distro_id,
                                                         os.path.basename(x))}
                                   for x in files],
                            url_root=url_root,
                            rst=self.rst_format)
        res = werkzeug.Response(tmpl.render(version=__version__, **kwargs),
                                content_type='text/html; charset=UTF-8')
        return res(environ, start_response)

    def rst_format(self, s):
        published = docutilscore.publish_parts(
            s, settings_overrides={'halt_level': 10},
            writer_name='html')
        return '<div class="rst">'+published['html_body']+'</div>'

    def __call__(self, environ, start_response):
        pypi.active_info.username = environ.get('REMOTE_USER', None)
        self.logger.debug('Handling request as [%s]'
                          % (pypi.active_info.username or 'NOT_AUTHENITCATED'))
        res = super(PyPiInnerApp, self).__call__(environ, start_response)
        return res

    def respond_login(self, req):
        remote_user = req.environ.get('REMOTE_USER', None)
        if remote_user:
            raise utils.NonCachedRedirect(req.url_root)

        return werkzeug.Response('Unauthorized', status=401,
                                 headers=utils.NO_CACHE_HEADERS)

    def respond_logout(self, req):
        return werkzeug.Response('Unauthorized', status=401)

    def respond_update_roles(self,req):
        username = req.values.get('username', '')
        distro_id = req.values.get('distro_id', '')
        roles = req.values.get('roles', '').split()
        groupname = req.values.get('groupname', '')
        self.pypi.security_manager.update_roles(distro_id=distro_id,username=username,roles=roles,groupname=groupname) 
        raise routing.RequestRedirect(req.url_root)
        
    @protect
    def respond_users(self, req):
        #if using config
        config = ConfigParser.ConfigParser() 
        try:
           config.read(self.top.security_config)
           f = open(config.get('plugin:htpasswd','filename'))
           user_list = [user.split(':')[0] for user in f]
           user_list.sort()
        #fallback to local database 
        except TypeError :
            user_list = self.pypi.security_manager.get_users()
            user_list = [user.username for user in user_list] 
        remote_user = req.environ.get('REMOTE_USER', None)
        tmpl = self.templates.get_template('users.html', req.environ)
        res = werkzeug.Response(tmpl.render(remote_user=remote_user,
                                            user_list=user_list,
                                            version=__version__),
                                content_type='text/html; charset=UTF-8',
                                )
        return res

    @protect
    def respond_adduser(self, req):
        username = req.values.get('username', '')
        password = req.values.get('password', '')
        #XXX repeating ourselves, 
        config = ConfigParser.ConfigParser() 
        config.read(self.top.security_config)
        f = config.get('plugin:htpasswd','filename')
        pfile = htpasswd.HtpasswdFile(f)
        pfile.update(username,password)
        pfile.save()
        raise routing.RequestRedirect('/users')

    def respond_pypi_action(self, req):
        remote_user = req.environ.get('REMOTE_USER', None)
        if not remote_user:
            res = werkzeug.Response('Unauthorized', status=401)
            return res

        params = req.values.to_dict()
        params.update(req.files)
        action = params.pop(':action')

        try:
            self.pypi.perform_action(action, **params)
            res = werkzeug.Response(content_type='text/plain; charset=UTF-8')
            res.response = 'OK'
        except model.NoSuchDistroError, err:
            res = HTTPNoSuchDistroError(err.distro_id)
            res.respose = str(err)
        except pypi.SecurityError, err:
            res = werkzeug.Response('Forbidden', 403)
            res.response = str(err)
        except pypi.PyPiError, err:
            res = werkzeug.Response('Forbidden', 403)
            res.response = str(err)

        return res


class VirtualHostMiddleware(object):
    """Simple prefix based virtual-host-fixing middleware.

      >>> vh = VirtualHostMiddleware('http://somehost.com/foo',
      ...                            lambda x, y: None)
      >>> env = {}
      >>> vh(env, None)
      >>> env['HTTP_HOST']
      'somehost.com'
      >>> env['SERVER_NAME']
      'somehost.com'
      >>> env['SCRIPT_NAME']
      '/foo/'
    """

    def __init__(self, baseurl, app, logger=utils.logger):
        self.baseurl = baseurl
        self.app = app
        self.logger = logger

    def __call__(self, environ, start_response):
        if not self.baseurl:
            return self.app(environ, start_response)

        req = werkzeug.Request(environ)
        script_name = new_script_name = environ.get('SCRIPT_NAME', '')
        http_host = new_http_host = environ.get('HTTP_HOST', '')

        if self.baseurl.startswith('/'):
            new_script_name = self.baseurl
        else:
            parts = self.baseurl.split('/')
            new_script_name = '/'.join(parts[3:]) + script_name
            new_http_host = parts[2]
        if not new_script_name.startswith('/'):
            new_script_name = '/' + new_script_name
        if not new_script_name.endswith('/'):
            new_script_name += '/'

        environ['SCRIPT_NAME'] = new_script_name
        environ['HTTP_HOST'] = environ['SERVER_NAME'] = new_http_host

        self.logger.debug('Fixed script_name to be: %s'
                          % new_script_name)
        self.logger.debug('Fixing host to be: %s'
                          % new_http_host)

        return self.app(environ, start_response)


class PyPiApp(object):
    """The main pypi app that is wrapped properly according to
    configuration.  Also ensures the current user info is
    setup.

      >>> app = PyPiApp(None)
    """

    pypi_factory = staticmethod(pypi.PyPi)

    def __init__(self,
                 basefiledir,
                 baseurl=None,
                 security_config=None,
                 sqluri='sqlite:///cluerelmgr.db',
                 self_register=False,
                 backup_pypis=[],
                 logger=utils.logger,
                 securelogger=utils.securelogger,
                 debug=False):
        self.logger = logger
        self.securelogger = securelogger
        self.basefiledir = basefiledir
        self.baseurl = baseurl
        self.security_config = security_config
        self.sqluri = sqluri
        self.self_register = self_register
        self.backup_pypis = backup_pypis
        self.debug = debug

        self.whoconfig, self.usermanager, self.groupmanager \
                        = self.build_secure_config()

    def build_secure_config(self):
        config = repozewhoconfig.WhoConfig(os.getcwd())
        if self.security_config is None:
            config.identifiers = [('basicauth',
                                   basicauth.BasicAuthPlugin('pypi'))]

            def factory(engine=self.pypi.engine):
                return engine.raw_connection()

            config.authenticators = [('sqlauth', sql.SQLAuthenticatorPlugin
                ('SELECT username, password FROM users WHERE username=:login',
                 factory,
                 None))]
            config.challengers = config.identifiers
            config.mdproviders = []
        else:
            self.securelogger.info('Using "%s" for security/repoze.who '
                                   'configuration' % self.security_config)
            with open(self.security_config) as f:
                config.parse(f)

        usermanager = None
        groupmanager = None
        for name, plugin in config.authenticators:
            if isinstance(plugin, repozehtpasswd.HTPasswdPlugin):
                usermanager = securehtpasswd.HtpasswdUserManager(plugin.filename)
                groupf = os.path.join(os.path.dirname(plugin.filename),
                                      'groups.info')
                self.securelogger.info('Using "%s" for users' \
                                        % plugin.filename)
                self.securelogger.info('Using "%s" for groups' % groupf)

                groupmanager = groupfile.FileGroupManager(groupf)
                break

        if usermanager is None:
            self.securelogger.warn('Web-based management of '
                                   'users/groups disabled')
            self.securelogger.warn('Web-based management only supported '
                                   'with htpasswd-style setup')

        return config, usermanager, groupmanager

    @werkzeug.cached_property
    def pypi(self):
        return self.pypi_factory(self.basefiledir,
                                 self.sqluri,
                                 self.self_register)

    @werkzeug.cached_property
    def app(self):
        innerapp = PyPiInnerApp(pypi=self.pypi, backup_pypis=self.backup_pypis,
                                debug=self.debug)
        innerapp.logger = self.logger

        app = whomiddleware.PluggableAuthenticationMiddleware(
            innerapp,
            self.whoconfig.identifiers,
            self.whoconfig.authenticators,
            self.whoconfig.challengers,
            self.whoconfig.mdproviders,
            classifiers.default_request_classifier,
            classifiers.default_challenge_decider,
            log_stream = self.securelogger,
            log_level = self.securelogger.getEffectiveLevel(),
            )
        if self.baseurl:
            app = VirtualHostMiddleware(self.baseurl, app)

        # we want as minimal checks as possible for static data
        # -- no security, no vh, etc
        app = werkzeug.SharedDataMiddleware(
            app, {'/static': ('clue.relmgr', 'static'),
                  '/dojo': ('cluedojo', 'static')})
        app = securewsgi.make_middleware({},
                                         app=app,
                                         usermanager=self.usermanager,
                                         groupmanager=self.groupmanager)
        innerapp.top = app
        #need this var exposed for user adding, should it be part of pypi constructor?
        app.security_config = self.security_config

        if self.usermanager is not None:
            innerapp.templates.can_manage_security = True

        return app

    def __call__(self, environ, start_response):
        return self.app(environ, start_response)


def make_app(global_conf, *args, **kwargs):
    return PyPiApp(*args, **kwargs)
