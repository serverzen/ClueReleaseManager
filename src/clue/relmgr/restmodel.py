import os
from restish import app, http, resource
import simplejson
from clue.relmgr import utils
import datetime


def simple_ser(ob):
    if ob is None:
        return ob
    if isinstance(ob, datetime.datetime):
        return ob.strftime('%Y-%m-%dT%H:%M:%S')
    raise TypeError(str(type(ob)))


def to_jsons(ob):
    '''Dump the given object as a JSON string.

      >>> class Mock(object):
      ...     def __init__(self, **kw):
      ...         self.__dict__.update(kw)

      >>> m = Mock(foo=1)
      >>> m._bar = 2
      >>> m.grr = 3

      >>> to_jsons(m)
      '{"foo": 1, "grr": 3}'
    '''

    d = dict(ob.__dict__)
    for x in d.keys():
        if x.startswith('_'):
            del d[x]
    return simplejson.dumps(d, default=simple_ser)


class DistrosRoot(resource.Resource):
    '''Root resource for all distros.

      >>> class Mock(object):
      ...     def __init__(self, **kw):
      ...         self.__dict__.update(kw)
      >>> root = DistrosRoot(Mock(get_distros=lambda x: []))
      >>> root.child_distro(None, [], None)
      (<clue.relmgr.restmodel.Distro object at ...>, [])
      >>> root.json(Mock(params={},
      ...                url=None))
      <Response at ... 200 OK>
    '''

    def __init__(self, pypi):
        self.pypi = pypi

    @resource.child('{distro_id}')
    def child_distro(self, req, segments, distro_id):
        return Distro(self.pypi, distro_id), segments

    @resource.GET(accept='application/json')
    def json(self, req):
        page_num = int(req.params.get('page_num', 1))
        search = req.params.get('search', None)
        distreq = req.params.get('req', None)
        base_url = req.url
        if distreq:
            reqs = self.pypi.find_req(distreq)
            distros = []
            for d, files in reqs:
                distros.append({'id': d.distro_id,
                                'name': d.name,
                                'last_updated': simple_ser(d.last_updated),
                                'summary': d.summary,
                                'files': [{'filename': os.path.basename(f),
                                           'url': req.relative_url(d.distro_id + '/f/'+os.path.basename(f), True),
                                           'version': v} for f, v in files]})
            total_pages = -1
            page_num = -1
        else:
            if search:
                results = self.pypi.search(search)
            else:
                results = self.pypi.get_distros('last_updated desc')
            page = utils.Page(results, page_num, 20)
            distros = [{'id': x.distro_id,
                        'name': x.name,
                        'last_updated': simple_ser(x.last_updated),
                        'summary': x.summary}
                       for x in page.results]
            total_pages = page.total_pages
            page_num = page.page_num

        jsonres = {'distros': distros,
                   'total_pages': total_pages,
                   'page_num': page_num}
        if search:
            jsonres['search'] = search
        return http.ok([], simplejson.dumps(jsonres))


class Distro(resource.Resource):
    '''A distro resource.

      >>> class Mock(object):
      ...     def __init__(self, **kw):
      ...         self.__dict__.update(kw)

      >>> class MockPyPi(object):
      ...     def get_distro(self, distro_id):
      ...         return Mock(distro_id=distro_id)

      >>> d = Distro(MockPyPi(), None)
      >>> d.distro
      <clue.relmgr.restmodel.Mock ...>
      >>> d.files_resource(None, [])
      (<clue.relmgr.restmodel.FilesRoot object at ...>, [])
      >>> d.json(None)
      <Response at ... 200 OK>
    '''

    def __init__(self, pypi, distro_id):
        self.pypi = pypi
        self.distro_id = distro_id

    @property
    def distro(self):
        if not hasattr(self, '_distro'):
            self._distro = self.pypi.get_distro(self.distro_id)
        return self._distro

    @resource.child('f')
    def files_resource(self, req, segments):
        segments = [x for x in segments if x]
        return FilesRoot(self.pypi, self.distro), segments

    @resource.child('i')
    def indexes_resource(self, req, segments):
        segments = [x for x in segments if x]
        return IndexesRoot(self.pypi, self.distro), segments

    @resource.GET(accept='application/json')
    def json(self, req):
        return http.ok([], to_jsons(self.distro))


class FilesRoot(resource.Resource):

    def __init__(self, pypi, distro):
        self.pypi = pypi
        self.distro = distro

    @resource.child('{filename}')
    def child_file(self, req, segments, filename):
        for full in self.pypi.get_files(self.distro.distro_id):
            if os.path.basename(full) == filename:
                return File(self.pypi, self.distro, filename), segments
        raise http.NotFoundError()

    @resource.GET(accept='application/json')
    def json(self, req):
        files = [os.path.basename(x)
                 for x in self.pypi.get_files(self.distro.distro_id)]
        return http.ok([], simplejson.dumps({'files': files}))


class File(resource.Resource):

    def __init__(self, pypi, distro, filename):
        self.pypi = pypi
        self.distro = distro
        self.filename = filename

    @resource.GET(accept='application/json')
    def json(self, req):
        for full in self.pypi.get_files(self.distro.distro_id):
            if os.path.basename(full) == self.filename:
                return http.ok([],
                               self.get_file_info(full))
        raise http.NotFoundError()

    def get_file_info(self, filename):
        base = os.path.basename(filename)
        st = os.stat(filename)
        return simplejson.dumps({'filename': base,
                                 'size': st.st_size})


class IndexesRoot(resource.Resource):

    def __init__(self, pypi, distro):
        self.pypi = pypi
        self.distro = distro

    @resource.child('{indexname}')
    def child_index(self, req, segments, indexname):
        for index in self.pypi.get_indexes(self.distro.distro_id):
            if index == indexname:
                return Index(self.pypi, self.distro, indexname), segments
        raise http.NotFoundError()

    @resource.POST(accept='application/json')
    def post(self, req):
        updated = simplejson.loads(req.body or '{}')
        indexname = updated['indexname']
        index = Index(self.pypi, self.distro, indexname)
        return index.save(req)

    @resource.PUT(accept='application/json')
    def put(self, req):
        distro_id = self.distro.distro_id
        updated = simplejson.loads(req.body or '{}')

        altered = []
        for indexdict in updated['indexes']:
            indexname = indexdict['indexname']
            altered.append(indexname)
            entries = indexdict['entries']

            self.pypi.index_manager.remove_index(distro_id, indexname)
            for x in entries:
                target_name, opt, target_version = utils.parse_req_parts(x)
                if opt not in ('==', '='):
                    raise ValueError('Bad req option "%s" for "%s"' %
                                     (str(opt), x))
                target_distro_id = utils.make_distro_id(target_name)
                self.pypi.index_manager.add_index_item(distro_id,
                                                       indexname,
                                                       target_distro_id,
                                                       target_version)
        return http.ok([], simplejson.dumps({'indexes': altered}))

    @resource.GET(accept='application/json')
    def json(self, req):
        filter_indexname = req.params.get('indexname', None)
        base_url = '/'.join(req.url.split('/')[:-2])
        indexes = []
        for x in self.pypi.get_indexes(self.distro.distro_id):
            if not filter_indexname:
                indexes.append(x)
                continue
            if filter_indexname == x:
                index = Index(self.pypi, self.distro, x)
                indexes.append(index.get_index_dict(base_url))
        return http.ok([], simplejson.dumps({'indexes': indexes}))


class Index(resource.Resource):

    def __init__(self, pypi, distro, indexname):
        self.pypi = pypi
        self.distro = distro
        self.indexname = indexname

    def get_index_dict(self, base_url):
        index = self.pypi.get_index(self.distro.distro_id, self.indexname)
        entries = []
        for target_distro, distro, filename in index:
            target_distro_id = get_distro_id(target_distro)
            url = None
            name = None
            if filename is not None:
                url = '%s%s/f/%s' % (base_url, target_distro_id, filename)
                name = target_distro.name

            if not name:
                utils.logger.warn('Bad distro for: '+target_distro_id)
                continue

            req = name+'=='+utils.parse_version(filename)
            entries.append({'target_distro_id': target_distro_id,
                            'name': name,
                            'req': req,
                            'url': url})
        return {'indexname': self.indexname,
                'id': self.indexname,
                'entries': entries}

    @resource.PUT(accept='application/json')
    def put(self, req):
        return self.save(req)

    def save(self, req):
        distro_id = self.distro.distro_id
        indexname = self.indexname
        updated = simplejson.loads(req.body or '{}')
        entries = updated['entries']

        if self.pypi.index_manager.has_index(distro_id, indexname):
            self.pypi.index_manager.remove_index(distro_id, indexname)
        for x in entries:
            target_name, opt, target_version = utils.parse_req_parts(x)
            if opt not in ('==', '='):
                raise ValueError('Bad req option "%s" for "%s"' %
                                 (str(opt), x))
            target_distro_id = utils.make_distro_id(target_name)
            self.pypi.index_manager.add_index_item(distro_id,
                                                   indexname,
                                                   target_distro_id,
                                                   target_version)
        return http.ok([], simplejson.dumps({'entries': entries}))

    @resource.DELETE(accept='application/json')
    def delete(self, req):
        self.pypi.index_manager.remove_index(self.distro.distro_id,
                                             self.indexname)
        return http.ok([], simplejson.dumps({'indexname': self.indexname}))

    @resource.GET(accept='application/json')
    def json(self, req):
        base_url = '/'.join(req.url.split('/')[:-3])
        return http.ok([], simplejson.dumps(self.get_index_dict(base_url)))


def get_distro_id(distro):
    if isinstance(distro, basestring):
        return utils.make_distro_id(distro)
    return distro.distro_id


class app_factory(object):

    def __init__(self, pypi, debug=False):
        self.restishapp = app.RestishApp(DistrosRoot(pypi))
        self.debug = debug

    def __call__(self, environ, start_response):
        if self.debug:
            req = http.Request(environ)
            utils.logger.debug('[JSON request] %s %s' % (req.method, req.path))
        return self.restishapp(environ, start_response)
