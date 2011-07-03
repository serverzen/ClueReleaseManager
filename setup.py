from setuptools import setup

base_version = '0.4'

readme = open('README.rst').read().strip()
history = open('CHANGES.rst').read().strip()

url = 'http://projects.serverzen.com/pm/p/cluemapper/wiki/ClueReleaseManager'

setup(name='ClueReleaseManager',
      version=base_version,
      description="An implementation of a PyPi server",
      long_description=readme + "\n" + history,
      classifiers=[
          "Programming Language :: Python",
          "Topic :: Software Development :: Libraries :: Python Modules",
          ],
      keywords='',
      author='Rocky Burt',
      author_email='rocky@serverzen.com',
      url=url,
      license='BSD',
      package_dir={'': 'src'},
      packages=['clue'],
      include_package_data=True,
      zip_safe=False,
      test_suite="clue.relmgr.tests.test_suite",
      install_requires=[
          'setuptools',
          'SQLAlchemy >= 0.5',
          'repoze.who >= 1.0.8, <= 1.0.999',
          'Werkzeug >= 0.6',
          'Jinja2 >= 2.1',
          'docutils >= 0.5',
          'restish >= 0.9',
          'simplejson >= 2.0',
          'ClueDojo >= 1.4',
          ],
      entry_points={
          'console_scripts': [
              'cluerelmgr-server = clue.relmgr.main:main',
              'cluerelmgr-admin = clue.relmgr.cmdtool:main',
              ],
          },
      )
