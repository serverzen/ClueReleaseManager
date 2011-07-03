import logging
import optparse
import os
import subprocess
import sys

import pkg_resources

from clue.relmgr import utils, ve
from clue.relmgr.pypi import PyPi


class InsecurePyPi(PyPi):

    def has_role(self, distro_id, *roles):
        return True

    def get_active_user(self):
        return 'admin'


class Runner(object):
    """Cmdtool runner.

      >>> runner = Runner()
      >>> class Mock(object):
      ...     def __init__(self, **kw):
      ...         self.__dict__.update(kw)
      >>> class MockSecurity(object):
      ...     def update_user(self, *args, **kwargs): pass
      ...     def update_roles(self, *args, **kwargs): pass
      >>> runner.pypi_factory = lambda x, y: Mock(
      ...     security_manager=MockSecurity())

      >>> runner.main([], [])
      Usage: tests.py <cmd> [<arg1>, <arg2>...]
      <BLANKLINE>
          Where <cmd> can be:
              setupindex <distro_id> <indexname> <eggreq1> [<eggreq2> ...]
              updateuser <username> <password> <email> [<role1> <role2> ...]
              updategroup <groupname> [<role1> <role2> ...]
              updateusersgroups <username> <group1> [<group2> ...]
              updatedistperms --username --distro_id  --role
              make-distro-public <distro_id>
              adddistro [-u <user>:<role>] <filename_or_url>
              addfile <distro_id> <filename_or_url>
              addindexentry <distro_id> <indexname> <target_distro_id> <target_distro_version>
              delindexentry <distro_id> <indexname> <target_distro_id>
      <BLANKLINE>

      >>> runner.main(['updateuser', 'foo', 'bar', 'abc', 'role1'])
    """

    pypi_factory = staticmethod(InsecurePyPi)

    def split_roles(self, *args):
        roles = {}
        for arg in args:
            s = arg.split(':')
            distro_id = ''
            if len(s) == 2:
                distro_id = s[0]
                role = s[1]
            else:
                role = s[0]
            l = roles.get(distro_id, None)
            if l is None:
                l = set()
                roles[distro_id] = l
            l.add(role)
        return roles

    def main(self, args=None, extraargs=None):
        logging.basicConfig()

        usage = """%prog <cmd> [<arg1>, <arg2>...]

    Where <cmd> can be:
        setupindex <distro_id> <indexname> <eggreq1> [<eggreq2> ...]
        updateuser <username> <password> <email> [<role1> <role2> ...]
        updategroup <groupname> [<role1> <role2> ...]
        updateusersgroups <username> <group1> [<group2> ...]
        updatedistperms --username --distro_id  --role
        make-distro-public <distro_id>
        adddistro [-u <user>:<role>] <filename_or_url>
        addfile <distro_id> <filename_or_url>
        addindexentry <distro_id> <indexname> <target_distro_id> <target_distro_version>
        delindexentry <distro_id> <indexname> <target_distro_id>"""

        parser = optparse.OptionParser(usage=usage)

        if args is None:
            args = []
        if extraargs is None:
            extraargs = sys.argv[1:]

        allargs = args + extraargs

        if len(allargs) < 1:
            parser.print_usage()
            return

        cmd = allargs[0]
        params = allargs[1:]

        pypi = self.pypi_factory('files', 'sqlite:///cluerelmgr.db')

        if cmd == 'updateuser':
            roledict = self.split_roles(*params[3:])
            pypi.security_manager.update_user(params[0],
                                              params[1],
                                              params[2],
                                              roledict.get('', []))
            for distro_id, roles in roledict.items():
                pypi.security_manager.update_roles(distro_id=distro_id,
                                                   username=params[0],
                                                   roles=roles)
        elif cmd == 'updategroup':
            roledict = self.split_roles(*params[1:])
            pypi.security_manager.update_group(params[0],
                                               roledict.get('', []))
            for distro_id, roles in roledict.items():
                pypi.security_manager.update_roles(distro_id=distro_id,
                                                   groupname=params[0],
                                                   roles=roles)
        elif cmd == 'updateusersgroups':
            username = params[0]
            pypi.security_manager.update_users_groups(params[0],
                                                      params[1:])
        elif cmd == 'updatedistperms':
            parser = optparse.OptionParser()
            parser.add_option('-u', '--username',)
            parser.add_option('-d', '--distro_id',)
            parser.add_option('-r', '--roles',)
            options, args = parser.parse_args(params)
            pypi.security_manager.update_roles(distro_id=options.distro_id,
                                                   username=options.username,
                                                   roles=options.roles.split())
        elif cmd == 'make-distro-public':
            #convenience method for making distros public
            distro_id = params[0]
            pypi.security_manager.update_roles(distro_id=distro_id,
                                                   username='anonymous',
                                                   roles=['reader'])
        elif cmd == 'adddistro':
            parser = optparse.OptionParser()
            parser.add_option('-u', '--user-role',
                              dest='user_roles',
                              action='append',
                              help='Setup default user role',
                              default=[])
            options, args = parser.parse_args(params)
            self.adddistro(pypi, args[0], options.user_roles)
        elif cmd == 'addfile':
            self.addfile(pypi, params[0], params[1:])
        elif cmd == 'addindexentry':
            distro_id = params[0]
            indexname = params[1]
            target_distro_id = params[2]
            target_version = params[3]

            pypi.index_manager.add_index_item(distro_id, indexname,
                                              target_distro_id, target_version)
        elif cmd == 'delindexentry':
            distro_id = params[0]
            indexname = params[1]
            target_distro_id = params[2]

            pypi.index_manager.del_index_item(distro_id, indexname,
                                              target_distro_id)
        elif cmd == 'setupindex':
            parser = optparse.OptionParser()
            parser.add_option('-f', '--overwrite', dest='overwrite',
                              action='store_true',
                              help='Force overwrite',
                              default=False)
            options, args = parser.parse_args(params)
            self.setupindex(pypi, args[0], args[1], args[2:],
                            overwrite=options.overwrite)
        else:
            print "No such command: %s" % cmd

    def addfile(self, pypi, distro_id, filenames):
        files = [utils.get_content(x) for x in filenames]
        pypi.upload_files(distro_id, files)

    def adddistro(self, pypi, filename, user_roles=[]):
        name, ver = utils.parse_distro_from_filename(filename)

        env = ve.VirtualEnv.create()
        env.install_distro(filename)
        md = env.get_distro(name).get_metadata_dict('PKG-INFO')
        print
        print 'Updated metadata for: ' + md['Name']
        dictinfo = utils.pkg_info_as_distro(md)
        distro_id = utils.make_distro_id(name)
        pypi.update_metadata(**dictinfo)

        print 'Adding file for: ' + md['Name']
        self.addfile(pypi, distro_id, [filename])

        if user_roles:
            print 'Setting up default user roles for: ' + md['Name']
            mapping = {}
            for x in user_roles:
                username, role = x.split(':')
                if username not in mapping:
                    mapping[username] = []
                roles = mapping[username]
                roles.append(role)
            for username, roles in mapping.items():
                print '  %s: %s' % (username, ', '.join(roles))
                pypi.security_manager.update_roles(distro_id=distro_id,
                                                   username=username,
                                                   roles=roles)

    def setupindex(self, pypi, distro_id, indexname, reqs, overwrite=False):
        if len(reqs) == 0:
            raise ValueError('Please specify one or more requirements')

        if not overwrite and pypi.index_manager.has_index(distro_id,
                                                          indexname):
            raise ValueError('Index by the name of "%s" for distro "%s" '
                             'already exists, use --overwrite to overwrite'
                             % (indexname, distro_id))

        env = ve.VirtualEnv.create()
        env.install_distro('pip')
        pip_path = os.path.join(env.path, 'bin', 'pip')
        subprocess.call([pip_path, 'install'] + list(reqs))

        froze = subprocess.Popen([pip_path, 'freeze'],
                                 stdout=subprocess.PIPE).communicate()[0]

        print
        if overwrite and pypi.index_manager.has_index(distro_id, indexname):
            pypi.index_manager.remove_index(distro_id, indexname)
            print 'Removed existing index'

        index_reqs = [x.strip() for x in froze.split('\n') if x.strip()]
        for x in index_reqs:
            req = pkg_resources.Requirement.parse(x)
            pypi.index_manager.add_index_item(distro_id,
                                              indexname,
                                              req.project_name,
                                              req.specs[0][1])

        print 'Created index "%s" for distro "%s" with the ' \
              'following requirements' % (distro_id, indexname)
        for x in index_reqs:
            print '  ', x.strip()


main = Runner().main

if __name__ == '__main__':
    main()
