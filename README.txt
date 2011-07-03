.. -*-rst-*-

============
Introduction
============

ClueReleaseManager is an implementation of the PyPi server backend as provided
by http://pypi.python.org.  It uses SQLAlchemy (on top of sqlite by default)
to store all project metadata and the filesystem for storing project files.

Current Features
================

  * User registration via setuptools
  * File upload (ie eggs) via setuptools
  * Basic authentication based security
  * Simple index browsing

Upcoming Features
=================

  * Full http://pypi.python.org PyPi server compatibility

Requirements
============

  * Python 2.5
  * setuptools
  * SQLAlchemy 0.5rc4 or higher
  * repoze.who 1.0.8 or higher
  * Werkzeug 0.4 or higher (less than 0.5 which has issues)

Installation
============

Install using the ``easy_install`` tool such as::

  $ easy_install ClueReleaseManager

This will provide the ``cluerelmgr-server`` and ``cluerelmgr-admin`` scripts
which are the entry points for everything ClueReleaseManager.

Getting Started
===============

First User
----------

By default there are no security/access rules setup so uploading to
the ClueReleaseManager instance will not work.  The most important
step to getting ready is to create a new user with access::

  $ cluerelmgr-admin updateuser firstuser somepassword firstuser@localhost manager

This command creates a new user with the username "firstuser",
password "somepassword", and email "firstuser@localhost".  The "manager"
entry at the end gives this user complete access to this
ClueReleaseManager instance.

Launching Server
----------------

Now that we have the user created, we can go ahead and launch the server::

  $ cluerelmgr-server

First Upload -- standard distutils/setuptools
---------------------------------------------

First you need to configure your local distutils to use the new local pypi
server.  To do this, edit ``$HOME/.pypirc``::

  [server-login]
  username:firstuser
  password:somepassword

Next go into your new project and register it with the server::

  $ python setup.py register -r http://localhost:8080

And now that the project (or distro in ClueReleaseManager terms) is
registered, we can upload files::

  $ python setup.py bdist_egg sdist upload -r http://localhost:8080

Allowing Anonymous Access
-------------------------

There is a special user named *anonymous* that can also be given roles.  To
allow an anonymous user to view all distros, first add him to
a group::

  $ cluerelmgr-admin updateusersgroups anonymous common

And next give that group access global access by doing::

  $ cluerelmgr-admin updategroup common reader


Server Command-Line Options
---------------------------

::

    Usage: cluerelmgr-server [options]

    Options:
      -h, --help            show this help message and exit
      -p PORT, --port=PORT  Port to listen on, defaults to 8080
      -i HOST, --interface=HOST
                            Host to listen on, defaults to 0.0.0.0
      -b BASEFILEDIR, --basefiledir=BASEFILEDIR
                            Base directory to store uploaded files,
                            defaults to files
      -d, --debug           Activate debug mode
      -s, --self-register   Allow self-registration
      -u BASEURL, --baseurl=BASEURL
                            The base url used in case of proxying
      --security-config=SECURITY_CONFIG
                            Use a separate configuration file to declare
                            the repoze.who config. See
                            http://static.repoze.org/whodocs
                            /#middleware-configuration-via-config-file
                            for details.
      --backup-pypi=BACKUP_PYPIS
                            Python indexes to fall back to.  When backup
                            index servers are configured they will be
                            queried if the user browsing this server has
                            the adddistro role and the this server will
                            be updated with all metadata and files.

Credits
=======

Created and maintained by Rocky Burt <rocky@serverzen.com>.

