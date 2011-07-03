.. -*-rst-*-

=========
Changelog
=========

0.4 - Unreleased
================

Features
--------

  * New *adddistro* command for cluerelmgr-admin which will try setting up
    a new distro based on an sdist

  * Uses Dojo to update listing and searching in an ajax style

  * Updated to use Werzeug 0.6+

  * Uses ClueSecure to provide web-based user/group management

  * New web UI for managing indexes

Bugs
----

  * Fixed issue where certain browsers were caching /login redirect
    preventing logins from working.


0.3.3 - Sept 18, 2009
=====================

  * Updated README.txt to help with getting started

  * Users with the MANAGER role can now also register new projects
    (previously only users with ADD role could do this)

  * Added favicon.ico and updated the wsgi app to support serving this file

  * When viewing the project/distro listing, if no files are accessible the
    user is now told

  * Fixed bug with uploading files


0.3.2 - June 24, 2009
=====================

  * Updated requirements to require Werkzeug < 0.5

  * reStructuredText parsing now handles errors

  * Pointing distutils/setuptools to the index without
    the /simple suffix now works


0.3.1 - Apr 18, 2009
====================

  * Can now setup an index (admin setupindex) based on a virtualenv

  * Added batching/paging support for latest changed distros on
    main page

  * Uncoupled the user-group mapping from the user table for situations
    where there is no user table record (ie anonymous)

  * Added search support


0.3.0.1 - Jan 26, 2009
======================

  * Fixed issue where uploading via distutils was broken


0.3 - Jan 20, 2009
==================

  * New cluerelmgr-admin tool for managing the db

  * Added custom index support

  * Anonymous users can now be added access on a per-distro basis

  * Browsing index to see metadata now possible


0.2 - Jan 4, 2009
=================

  * Added --security_config option for specifying a separate security
    configuration based on repoze.who

  * Added -u option for specifying a proxied url

  * Added basic user-based security settings

0.1 - Dec 29, 2009
==================

  * Initial release

