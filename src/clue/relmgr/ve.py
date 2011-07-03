from __future__ import with_statement
import email
import logging
import os
import pkg_resources
import tempfile
import subprocess
import sys

try:
    import virtualenv
    virtualenv.logger = virtualenv.Logger([(logging.ERROR, sys.stdout)])
except ImportError, e:
    raise EnvironmentError('Please install "virtualenv"')


class Distro(object):

    def __init__(self, dist):
        self.dist = dist
        self._metadata = {}

    def get_metadata_dict(self, group):
        if not group in self._metadata:
            m = email.message_from_string(self.dist.get_metadata(group))
            md = {}
            for x, y in m.items():
                md[x] = y
            self._metadata[group] = md
        return self._metadata[group]


class VirtualEnv(object):

    @classmethod
    def create(cls, path=None, create_if_not_exist=False):
        if path is None:
            path = tempfile.mkdtemp()
        if create_if_not_exist and not os.path.exists(path):
            os.mkdirs(path)
        ve = cls(path)
        virtualenv.create_environment(path)
        return ve

    def __init__(self, path):
        self.path = path

    def install_distro(self, req):
        easy_install_path = os.path.join(self.path, 'bin', 'easy_install')
        subprocess.call([easy_install_path, req])

    @property
    def workingset(self):
        if not hasattr(self, '_workingset'):
            ver = '%i.%i' % (sys.version_info[0], sys.version_info[1])
            site_packages = os.path.join(self.path, 'lib',
                                         'python'+ver, 'site-packages')
            pypaths = [site_packages]
            for x in os.listdir(site_packages):
                if x.endswith('.pth'):
                    with open(os.path.join(site_packages, x), 'r') as f:
                        for y in f:
                            if y.startswith('#'):
                                continue
                            if y.startswith('import'):
                                continue
                            relpath = os.path.join(site_packages, y.strip())
                            pypaths.append(os.path.abspath(relpath))

            self._workingset = pkg_resources.WorkingSet(pypaths)
        return self._workingset

    def get_distro(self, reqstr):
        try:
            d = self.workingset.find(pkg_resources.Requirement.parse(reqstr))
            if d is not None:
                return Distro(d)
        except pkg_resources.VersionConflict:
            return None
        return None
