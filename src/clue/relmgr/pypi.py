from __future__ import with_statement
import os
import datetime
from clue.relmgr import model, utils
import sqlalchemy as sa
from sqlalchemy import orm
import threading
import pkg_resources
from setuptools import package_index

active_info = threading.local()


class PyPiError(Exception):
    pass


class MismatchedPasswordsError(PyPiError):
    pass


class MissingParamError(PyPiError):
    pass


class SecurityError(PyPiError):
    pass


ANONYMOUS = 'anonymous'

AUTHENTICATED_ROLE = 'authenticated'
READER_ROLE = 'reader'
MANAGER_ROLE = 'manager'
ADD_DISTRO_ROLE = 'adddistro'

VALID_REQ_SEP = ['>=', '<=', '==', '=']


def get_active_user():
    return getattr(active_info, 'username', None) or ANONYMOUS


class SimplePyPi(object):

    def __init__(self):
        self.distros = {}

    def get_distros(self):
        return self.distros.values()


def version_info(s):
    return pkg_resources.parse_version(os.path.basename(s))


class PyPi(object):
    """Represents standard pypi functionality.

      >>> pypi = PyPi('.', '', True)
      >>> class Mock(object):
      ...     def __init__(self, **kw):
      ...         self.__dict__.update(kw)
      >>> objs = {}
      >>> class MockSessionMaker(object):
      ...     def __init__(self, bind=None):
      ...         self.bind = bind
      ...         self.objs = objs
      ...     def query(self, s):
      ...         return self
      ...     def filter_by(self, **kwargs):
      ...         return self
      ...     def all(self):
      ...         return []
      ...     def add(self, o):
      ...         self.objs[o.username] = o
      ...     def commit(self):
      ...         pass
      ...     def first(self):
      ...         return None
      ...     def execute(self, *args, **kwargs):
      ...         return []
      ...     def __iter__(self):
      ...         return iter([])

      >>> pypi._sessionmaker = MockSessionMaker
      >>> pypi.register_user('foo', 'bar', 'bar', 'a')
      >>> objs
      {'foo': <clue.relmgr.model.SQLUser object ...>}

      >>> pypi.perform_action('file_upload', name='foo', content='bar')
      Traceback (most recent call last):
      ValueError: no such distro, "foo"
    """

    logger = utils.logger
    _engine = None
    _sessionmaker = None
    _security_manager = None
    _index_manager = None

    def __init__(self, basefiledir, sqluri, self_register=False):
        self.basefiledir = basefiledir
        self.sqluri = sqluri
        self.self_register = self_register

    @property
    def engine(self):
        if self._engine is None:
            self._engine = sa.create_engine(self.sqluri)
            model.metadata.create_all(self.engine)
        return self._engine

    def setup_model(self):
        # all that's required here is calling self.engine
        self.engine

    @property
    def sessionmaker(self):
        if self._sessionmaker is None:
            self._sessionmaker = orm.sessionmaker(bind=self.engine)
        return self._sessionmaker

    @property
    def security_manager(self):
        if self._security_manager is None:
            self._security_manager = model.SecurityManager(self.sessionmaker)
        return self._security_manager

    @property
    def index_manager(self):
        if self._index_manager is None:
            self._index_manager = model.IndexManager(self.sessionmaker)
        return self._index_manager

    def register_user(self, name, password, confirm, email):
        if not self.self_register:
            raise SecurityError('Server does not permit self-registration')

        if not name:
            raise MissingParamError(name)

        if not password:
            raise MissingParamError(password)

        if not confirm:
            raise MissingParamError(email)

        if password != confirm:
            raise MismatchedPasswordsError()

        if name == ANONYMOUS:
            raise PyPiError('Cannot register reserved "anonymous" username')

        self.security_manager.update_user(name, password, email)

    def perform_action(self, action='', **kwargs):
        if action not in self.actions:
            self.logger.error('Action "%s" is not handled by this server' %
                              action)
            raise PyPiError('Action "%s" is not handled by this server' %
                            action)
        action = self.actions.get(action)
        # the action method is unbound so we need to pass in self
        action(self, **kwargs)

    def get_active_user(self):
        return get_active_user()

    def has_role(self, distro_id, *roles):
        # any user that has authenticated gets magical AUTHENTICATED_ROLE
        if AUTHENTICATED_ROLE in roles and self.get_active_user() != ANONYMOUS:
            return True
        derived = self.security_manager.get_roles(self.get_active_user(),
                                                  distro_id, True)
        for x in roles:
            if x in derived:
                return True
        return False

    def update_metadata(self, name, **kwargs):
        distro_id = utils.make_distro_id(name)

        ses = self.sessionmaker()
        q = ses.query(model.SQLDistro)
        distro = q.filter_by(distro_id=distro_id).all()

        if len(distro) == 0:
            if not self.has_role(None, ADD_DISTRO_ROLE, MANAGER_ROLE):
                raise SecurityError('"%s" cannot add "%s" distro' %
                                    (self.get_active_user(), distro_id))
            distro = model.SQLDistro()
            utils.update_obj(distro, **kwargs)
            distro.distro_id = distro_id
            distro.owner = self.get_active_user()
            ses.add(distro)
            self.logger.debug('Creating new distro "%s"' % distro_id)
        else:
            distro = distro[0]
            if not self.has_role(distro_id, model.OWNER_ROLE, MANAGER_ROLE):
                raise SecurityError('"%s" cannot manage "%s" distro' %
                                    (self.get_active_user(), distro_id))
            self.logger.debug('Updating distro "%s"' % distro_id)
            utils.update_obj(distro, **kwargs)
        distro.name = name
        distro.last_updated = datetime.datetime.now()
        ses.commit()

    def update_updated(self, distro_id, last_updated=None):
        ses = self.sessionmaker()
        q = ses.query(model.SQLDistro)
        distro = q.filter_by(distro_id=distro_id).first()
        if last_updated is None:
            last_updated = datetime.datetime.now()
        distro.last_updated = last_updated
        ses.commit()

    def upload_files(self, name, content, **kwargs):
        distro_id = utils.make_distro_id(name)
        distro = self.get_distro(distro_id)
        if not self.has_role(distro_id, model.OWNER_ROLE, MANAGER_ROLE):
            raise SecurityError('"%s" is not the owner of "%s" distro' %
                                (self.get_active_user(), distro_id))

        targetdir = os.path.join(self.basefiledir, distro_id[0],
                                 distro_id)
        if not os.path.exists(targetdir):
            os.makedirs(targetdir)
        if not isinstance(content, (list, tuple)):
            content = [content]

        for content_item in content:
            target = os.path.join(targetdir, content_item.filename)
            content_item.save(target)
            self.logger.debug('Added file "%s" to "%s"' %
                              (content_item.filename, distro_id))

        self.update_updated(distro_id)

    def get_indexes(self, distro_id):
        return [x for x in self.index_manager.get_indexes(distro_id)]

    def get_index(self, distro_id, indexname):
        if not self.has_role(distro_id,
                             READER_ROLE, MANAGER_ROLE, model.OWNER_ROLE):
            raise SecurityError('Permission denied')

        indexes = self.index_manager.get_indexes(distro_id)
        index = indexes[indexname]
        res = []
        for reqstr in index:
            if reqstr.startswith('!'):
                res.append((reqstr[1:], None, None))
                continue
            req = pkg_resources.Requirement.parse(reqstr)
            try:
                targetdistro = self.get_distro(distro_name=req.project_name)
            except SecurityError, exc:
                res.append((reqstr, None, None))
                continue

            targetdir = os.path.join(self.basefiledir,
                                     targetdistro.distro_id[0],
                                     targetdistro.distro_id)
            if not os.path.exists(targetdir):
                continue
            for fname in os.listdir(targetdir):
                for d in package_index.distros_for_filename(
                    os.path.join(targetdir, fname)):
                    if d.version == req.specs[0][1]:
                        res.append((targetdistro, d, fname))
        return res

    def find_req(self, reqstr, order_by='distro_id'):
        ses = self.sessionmaker()
        query = ses.query(model.SQLDistro)

        pkgreqs = [x for x in pkg_resources.parse_requirements(reqstr)]
        reqs = [model.SQLDistro.distro_id == \
                  utils.make_distro_id(x.project_name)
                for x in pkgreqs]
        query = query.filter(sa.or_(*reqs))

        if order_by is not None:
            vals = []
            for x in order_by.split(','):
                vals.append('distros_'+x.strip())
            query = query.order_by(','.join(vals))

        distros = [x for x in query
                   if self.has_role(x.distro_id,
                                    READER_ROLE, MANAGER_ROLE,
                                    model.OWNER_ROLE)]

        res = []
        for distro in distros:
            entries = []
            for f in self.get_files(distro.distro_id):
                version = utils.parse_version(f)
                if version:
                    for r in pkgreqs:
                        if version in r:
                            entries.append((f, version))
                            break
            if entries:
                res.append((distro, entries))

        return res

    def search(self, s, order_by='distro_id'):
        ses = self.sessionmaker()
        query = ses.query(model.SQLDistro)

        expr = '%%%s%%' % s
        query = query.filter(sa.or_(model.SQLDistro.name.like(expr),
                                    model.SQLDistro.description.like(expr),
                                    model.SQLDistro.summary.like(expr)))

        if order_by is not None:
            vals = []
            for x in order_by.split(','):
                vals.append('distros_'+x.strip())
            query = query.order_by(','.join(vals))

        distros = [x for x in query
                   if self.has_role(x.distro_id,
                                    READER_ROLE, MANAGER_ROLE,
                                    model.OWNER_ROLE)]
        return distros

    def get_distros(self, order_by=None):
        ses = self.sessionmaker()
        query = ses.query(model.SQLDistro)
        if order_by is not None:
            vals = []
            for x in order_by.split(','):
                vals.append('distros_'+x.strip())
            query = query.order_by(','.join(vals))

        distros = [x for x in query
                   if self.has_role(x.distro_id,
                                    READER_ROLE, MANAGER_ROLE,
                                    model.OWNER_ROLE)]
        return distros

    def get_distro(self, distro_id=None, distro_name=None):
        if not distro_id:
            distro_id = utils.make_distro_id(distro_name)

        try:
            if not self.has_role(distro_id,
                                 READER_ROLE, MANAGER_ROLE, model.OWNER_ROLE):
                raise SecurityError('Permission denied')
        except ValueError, err:
            return None

        ses = self.sessionmaker()
        q = ses.query(model.SQLDistro)
        if distro_name:
            distro_id = utils.make_distro_id(distro_name)
        return q.filter_by(distro_id=distro_id).first()

    def get_files(self, distro_id):
        if not self.has_role(distro_id,
                             READER_ROLE, MANAGER_ROLE, model.OWNER_ROLE):
            raise SecurityError('Permission denied')

        if isinstance(distro_id, model.SQLDistro):
            distro_id = distro_id.distro_id
        distrodir = os.path.join(self.basefiledir, distro_id[0], distro_id)

        res = []
        if os.path.exists(distrodir):
            for fname in os.listdir(distrodir):
                res.append(os.path.join(distrodir, fname))
        # sort so that latest versions come first
        res.sort(lambda x, y: cmp(version_info(x),
                                  version_info(y)),
                 reverse=True)
        return res

    def get_file(self, distro_id, fname):
        if not self.has_role(distro_id,
                             READER_ROLE, MANAGER_ROLE, model.OWNER_ROLE):
            raise SecurityError('Permission denied')

        distrodir = os.path.join(self.basefiledir, distro_id[0], distro_id)
        return os.path.join(distrodir, fname)


    actions = {
        'submit': update_metadata,
        'user': register_user,
        'file_upload': upload_files,
        }
