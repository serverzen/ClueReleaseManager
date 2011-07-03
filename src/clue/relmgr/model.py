from __future__ import with_statement
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy import sql
from sqlalchemy.ext import declarative

from clue.relmgr import utils

Base = declarative.declarative_base()
metadata = Base.metadata


users_groups_table = sa.Table(
    'users_groups', metadata,
    sa.Column('username', sa.String, sa.ForeignKey('users.username'),
              primary_key=True),
    sa.Column('groupname', sa.String, sa.ForeignKey('groups.groupname'),
              primary_key=True),
    )


def _u(s):
    if isinstance(s, unicode):
        return s
    return unicode(s, 'utf-8')


class NoSuchDistroError(Exception):

    def __init__(self, distro_id):
        self.distro_id = distro_id
        super(NoSuchDistroError, self).__init__(u'No such distro "%s"'
                                                % distro_id)


class SQLUser(Base):
    """A user.

      >>> u = SQLUser()
    """

    __tablename__ = 'users'

    def __init__(self, username=None):
        self.username = username

    username = sa.Column(sa.String, primary_key=True)
    password = sa.Column(sa.String)
    email = sa.Column(sa.String)

    groups = orm.relation('SQLGroup', secondary=users_groups_table)


class SQLDistro(Base):
    """A project distribution.

      >>> d = SQLDistro()
    """

    __tablename__ = 'distros'

    def __init__(self, distro_id=None, name=None):
        if distro_id is not None:
            self.distro_id = distro_id
        if name is not None:
            self.name = name

    distro_id = sa.Column(sa.String, primary_key=True)
    name = sa.Column(sa.String)
    owner = sa.Column(sa.String)
    author = sa.Column(sa.String)
    author_email = sa.Column(sa.String)
    classifiers = sa.Column(sa.String)
    description = sa.Column(sa.String)
    download_url = sa.Column(sa.String)
    home_page = sa.Column(sa.String)
    keywords = sa.Column(sa.String)
    license = sa.Column(sa.String)
    metadata_version = sa.Column(sa.String)
    platform = sa.Column(sa.String)
    summary = sa.Column(sa.String)
    version = sa.Column(sa.String)
    last_updated = sa.Column(sa.DateTime)


class SQLGroup(Base):
    __tablename__ = 'groups'

    def __init__(self, groupname=None):
        self.groupname = groupname

    groupname = sa.Column(sa.String, primary_key=True)

    users = orm.relation('SQLUser', secondary=users_groups_table)

    def __repr__(self):
        return '<SQLGroup %r>' % self.groupname


class SQLRoleMapping(Base):
    """A mapping of roles to userse.

      >>> mapping = SQLRoleMapping()
    """

    __tablename__ = 'rolemappings'

    def __init__(self, role=None, distro_id=None, username=None,
                 groupname=None):
        if role is not None:
            self.role = role
        if distro_id is not None:
            self.distro_id = distro_id
        if username is not None:
            self.username = username
        if groupname is not None:
            self.groupname = groupname

    role = sa.Column(sa.String, primary_key=True)
    distro_id = sa.Column(sa.String, sa.ForeignKey('distros.distro_id'),
                          primary_key=True)
    username = sa.Column(sa.String, sa.ForeignKey('users.username'),
                         primary_key=True)
    groupname = sa.Column(sa.String, sa.ForeignKey('groups.groupname'),
                          primary_key=True)

    user = orm.relation(SQLUser, primaryjoin=username==SQLUser.username)
    distro = orm.relation(SQLDistro,
                          primaryjoin=distro_id==SQLDistro.distro_id)
    group = orm.relation(SQLGroup,
                         primaryjoin=groupname==SQLGroup.groupname)


OWNER_ROLE = 'owner'


class SecurityManager(object):
    """A tool for querying security.

    Example usage would be as follows:

      >>> sm = SecurityManager(sessionmaker)

    At first there would be no roles for the foobar user since the user
    hasn't been added to the db yet.

      >>> sm.get_roles('foobar')
      set([u'authenticated'])

    So now we add users.

      >>> ses = sessionmaker()
      >>> ses.add(SQLUser('foobar'))

    And some roles.

      >>> ses.add(SQLRoleMapping('manager', '', 'foobar', ''))
      >>> ses.commit()

      >>> sm.get_roles('foobar')
      set([u'manager', u'authenticated'])

    Next we add some groups with roles.

      >>> ses.add(SQLGroup('group1'))
      >>> ses.add(SQLGroup('group2'))
      >>> ses.add(SQLRoleMapping('reader1', '', '', 'group1'))
      >>> ses.add(SQLRoleMapping('reader2', '', '', 'group2'))
      >>> u = ses.query(SQLUser).filter_by(username='foobar').first()
      >>> g = ses.query(SQLGroup).filter_by(groupname='group2').first()
      >>> u.groups.append(g)
      >>> ses.commit()

      >>> sm.get_roles('foobar')
      set([u'manager', u'authenticated', u'reader2'])

    So far it's just been querying global roles.  Distro-specific
    roles should work similarly.

      >>> sm.get_roles('foobar', 'distro1')
      Traceback (most recent call last):
      ValueError: no such distro, "distro1"

      >>> ses.add(SQLDistro('distro1', 'Distro 1'))
      >>> ses.commit()
      >>> sm.get_roles('foobar', 'distro1')
      set([u'authenticated'])

      >>> ses.add(SQLRoleMapping('reader3', 'distro1', '', 'group2'))
      >>> ses.commit()
      >>> sm.get_roles('foobar', 'distro1')
      set([u'authenticated', u'reader3'])

    And now for groups.

      >>> sm.update_users_groups('foobar', ['group1', 'group2'])
      >>> ses.query(SQLUser).filter_by(username='foobar').first().groups
      [<SQLGroup u'group1'>, <SQLGroup u'group2'>]
    """

    logger = utils.logger

    def __init__(self, sessionmaker):
        self.sessionmaker = sessionmaker

    def get_roles(self, username, distro_id=None, also_global=False):
        ses = self.sessionmaker()
        roles = set()
        self._populate_roles(ses, roles, username, distro_id, also_global)

        if (not username) or username == 'anonymous':
            roles.add(u'anonymous')
        else:
            roles.add(u'authenticated')
            # add anonymous roles too
            self._populate_roles(ses, roles, u'anonymous',
                                 distro_id, also_global)

        return roles

    def _populate_roles(self, ses, roles, username, distro_id, also_global):
        distro = distro_id

        rows = ses.execute(
            'select groupname from users_groups where username=:username',
            {'username': username})
        checks = [{'groupname': x[0]} for x in rows]
        checks.append({'username': username})

        query = ses.query(SQLRoleMapping)
        if distro_id is None or also_global:
            for check in checks:
                for x in query.filter_by(distro_id='', **check):
                    roles.add(x.role)

        if distro_id is None:
            return

        if isinstance(distro, basestring):
            q = ses.query(SQLDistro)
            distro = q.filter_by(distro_id=distro_id).first()
            if distro is None:
                raise NoSuchDistroError(distro_id)

        if username == distro.owner:
            roles.add(OWNER_ROLE)

        for check in checks:
            for x in query.filter_by(distro_id=distro.distro_id,
                                     **check):
                roles.add(x.role)

    def update_user(self, name, password, email, roles=[]):
        ses = self.sessionmaker()
        u = ses.query(SQLUser).filter_by(username=name).first()
        if u is None:
            u = SQLUser()
            u.username = name
            ses.add(u)

        u.username = name
        u.password = password
        u.email = email

        self._update_roles(ses, groupname=name, roles=roles)

        ses.commit()
        self.logger.info('User "%s" updated' % name)

    def update_group(self, name, roles=[]):
        ses = self.sessionmaker()
        g = ses.query(SQLGroup).filter_by(groupname=name).all()
        if len(g) == 0:
            g = SQLGroup()
            g.groupname = name
            ses.add(g)

        self._update_roles(ses, groupname=name, roles=roles)

        ses.commit()
        self.logger.info('Group "%s" updated' % name)

    def update_roles(self, distro_id='', username='',
                     groupname='', roles=[]):
        ses = self.sessionmaker()
        self._update_roles(ses, distro_id, username, groupname, roles)
        ses.commit()

        if groupname:
            self.logger.info('Roles for group "%s" updated' % groupname)
        if username:
            self.logger.info('Roles for user "%s" updated' % username)

    def get_groups(self, username):
        ses = self.sessionmaker()
        groupquery = ses.query(SQLGroup).filter_by
        s = sql.select([users_groups_table.c.groupname],
                       users_groups_table.c.username==username)
        groups = set()
        for row in ses.execute(s):
            g = groupquery(groupname=row[0]).one()
            groups.add(g.groupname)
        return groups

    def get_users(self):
        ses = self.sessionmaker()
        users = ses.query(SQLUser).all()
        return users

    def update_users_groups(self, username, groups):
        username = _u(username)
        groups = [_u(x) for x in groups]

        ses = self.sessionmaker()

        groupdict = {}
        groupquery = ses.query(SQLGroup).filter_by
        s = sql.select([users_groups_table.c.groupname],
                       users_groups_table.c.username==username)
        for row in ses.execute(s):
            g = groupquery(groupname=row[0]).one()
            groupdict[g.groupname] = g

        g1 = set(groupdict.keys())
        g2 = set(groups)
        if g1 == g2:
            self.logger.info('Groups for user "%s" unchanged since no '
                             'changes needed' % username)
            return

        self.logger.info('original: ' + ', '.join(g1))
        self.logger.info('new: ' + ', '.join(g2))
        ses.execute(users_groups_table.delete().where(
            users_groups_table.c.username==username))

        keys = groupdict.keys()
        for x in keys:
            if x not in groups:
                del groupdict[x]

        for g in groups:
            if g not in groupdict:
                newgroup = ses.query(SQLGroup).filter_by(groupname=g).first()
                if newgroup is None:
                    newgroup = SQLGroup()
                    newgroup.username = username
                    newgroup.groupname = g
                    self.logger.info('Created new group: ' + g)
                    ses.add(newgroup)

                groupdict[g] = newgroup

        for gname, group in groupdict.items():
            s = users_groups_table.insert().values(
                username=username, groupname=gname)
            ses.execute(s)
        ses.commit()

        self.logger.info('Groups for user "%s" updated' % username)

    def _update_roles(self, ses, distro_id='',
                      username='', groupname='', roles=[]):

        assert username or groupname

        kwargs = {'distro_id': distro_id,
                  'groupname': groupname,
                  'username': username}
        if username:
            assert not groupname
            kwargs['username'] = username
        elif groupname:
            assert not username
            kwargs['groupname'] = groupname

        q = ses.query(SQLRoleMapping)
        res = q.filter_by(**kwargs)

        remaining = []
        all = []
        for mapping in res:
            all.append(mapping.role)
            if mapping.role not in roles:
                ses.delete(mapping)
                continue
            remaining.append(mapping.role)

        if set(remaining) != roles:
            for role in roles:
                if role in remaining:
                    continue
                r = SQLRoleMapping()
                utils.update_obj(r, **kwargs)
                r.role = role
                ses.add(r)


class SQLIndexItem(Base):
    __tablename__ = 'index_items'

    indexname = sa.Column(sa.String, primary_key=True)
    distro_id = sa.Column(sa.String, sa.ForeignKey('distros.distro_id'),
                          primary_key=True)

    target_distro_id = sa.Column(sa.String, sa.ForeignKey('distros.distro_id'),
                          primary_key=True)
    target_version = sa.Column(sa.String)


class IndexManager(object):
    """A manager for indexes.

    Example usage would be as follows:

      >>> im = IndexManager(sessionmaker)
      >>> im.get_indexes('foobar')
      {}

    Setup some initial data.

      >>> ses = sessionmaker()
      >>> ses.add(SQLDistro('distro1', 'Distro_1'))
      >>> ses.commit()

    No index items have been setup thus far.

      >>> im.get_indexes('distro1')
      {}

    Adding an index works with ``add_index_item``.

      >>> im.add_index_item('distro1', 'foobar', 'distro1', 'v1')
      >>> im.get_indexes('distro1')
      {u'foobar': [u'Distro_1==v1']}

    Deleting an index item works with ``del_index_item``.

      >>> im.del_index_item('distro1', 'foobar', 'distro1')
      >>> im.get_indexes('distro1')
      {}
    """

    def __init__(self, sessionmaker):
        self.sessionmaker = sessionmaker

    def get_indexes(self, distro_id):
        ses = self.sessionmaker()
        indexq = ses.query(SQLIndexItem)
        distroq = ses.query(SQLDistro)
        indexes = {}
        for x in indexq.filter_by(distro_id=distro_id):
            index = indexes.get(x.indexname)
            if index is None:
                index = indexes[x.indexname] = []
            d = distroq.filter_by(distro_id=x.target_distro_id).first()
            if d is None:
                index.append('!'+x.target_distro_id)
            else:
                index.append(d.name+'=='+x.target_version)

        return indexes

    def has_index(self, distro_id, index):
        ses = self.sessionmaker()
        indexq = ses.query(SQLIndexItem)
        q = indexq.filter_by(distro_id=distro_id, indexname=index)
        return q.first() is not None

    def remove_index(self, distro_id, index):
        ses = self.sessionmaker()
        indexq = ses.query(SQLIndexItem)
        q = indexq.filter_by(distro_id=distro_id, indexname=index)
        if q.first() is None:
            raise ValueError('No index with that name')

        for x in q:
            ses.delete(x)

        ses.commit()

    def add_index_item(self, distro_id, indexname,
                       target_distro_id, target_version):
        ses = self.sessionmaker()
        entry = SQLIndexItem()
        entry.distro_id = distro_id
        entry.indexname = indexname
        entry.target_distro_id = target_distro_id
        entry.target_version = target_version
        ses.add(entry)
        ses.commit()

    def del_index_item(self, distro_id, indexname,
                       target_distro_id):
        ses = self.sessionmaker()
        q = ses.query(SQLIndexItem)
        for item in q.filter_by(distro_id=distro_id, indexname=indexname,
                                target_distro_id=target_distro_id):
            ses.delete(item)
        ses.commit()
