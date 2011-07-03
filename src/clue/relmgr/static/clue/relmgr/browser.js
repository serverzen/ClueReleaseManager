dojo.provide('clue.relmgr.browser');

dojo.require('clue.relmgr.utils')
dojo.require('dojox.rpc.Service');
dojo.require('dojox.data.JsonRestStore');

dojo.declare('clue.relmgr.browser.URL', null, {
    
    constructor: function(url) {
        this.host_path = null;
        this.query_params = new Object();
        this.comment_params = new Object();

        var parts = url.split('#');
        var left = url;
        if (parts.length > 1) {
            var comment_string = parts[1];
            this.comment_params = this._split_kwargs(comment_string);
            left = parts[0];
        }

        parts = left.split('?');
        if (parts.length > 1) {
            var query_string = parts[1];
            this.query_params = this._split_kwargs(query_string);
            left = parts[0];
        }

        this.host_path = left;
    },

    _split_kwargs: function(s) {
        var vars = s.split('&');
        var kwargs = new Object();

        for (var i = 0; i < vars.length; i++) {
            var pair = vars[i].split("=");
            kwargs[pair[0]] = pair[1]
        }

        return kwargs;
    },

    _obj_as_kwargstr: function(obj) {
        var s = '';
        for (k in obj) {
            s = s + '&' + k + '=' + obj[k];
        }

        if (s.length > 0 && s.charAt(0) == '&')
            s = s.substring(1);
        return s;
    },

    get_query_string: function() {
        return this._obj_as_kwargstr(this.query_params);
    },

    get_comment_string: function() {
        return this._obj_as_kwargstr(this.comment_params);
    },

    toString: function() {
        var s = this.host_path;
        var is_empty = clue.relmgr.utils.is_empty;
        if (!is_empty(this.query_params))
            s = s + '?' + this.get_query_string();
        if (!is_empty(this.comment_params))
            s = s + '#' + this.get_comment_string();
        return s;
    }
});

dojo.declare('clue.relmgr.browser.Browser', null, {
    constructor: function(base_url) {
        if (base_url != null & !base_url[-1] == '/')
            base_url = base_url + '/';
        this.base_url = base_url;
        var target = base_url+'d/';
        this.distro_store = new dojox.data.JsonRestStore({target: target});
        this.distro_store.syncMode = true;
    },

    activate: function() {
        dojo.query('.pager a.page-link').connect('onclick', dojo.hitch(this, function(e) {
            e.preventDefault();
            var url = new clue.relmgr.browser.URL(e.target.href);
            this.update_listing({page_num: url.query_params.page_num});
        }));

        dojo.query('.distro-searchform form').connect('onsubmit', dojo.hitch(this, function(e) {
            e.preventDefault();
            var ob = dojo.formToObject(e.target);
            this.perform_search(ob.s);
        }));

        var url = new clue.relmgr.browser.URL(window.location.href);
        var is_empty = clue.relmgr.utils.is_empty;
        if (!is_empty(url.comment_params)) {
            this.update_listing(url.comment_params);
            if (url.comment_params.search) {
                var input = dojo.query('.distro-searchform form input[name=s]')[0];
                dojo.attr(input, 'value', url.comment_params.search);
            }
        }
    },

    perform_search: function(s, page_num) {
        var query = {search: s};
        if (page_num)
            query.page_num = page_num;
        this.update_listing(query);
    },

    populate_listing: function(distros) {
        var tbody = dojo.query('table.distro-listing tbody')[0];

        dojo.empty(tbody);
        dojo.forEach(distros, dojo.hitch(this, function(distro) {
            var tr = dojo.create('tr');
            var distro_url = this.base_url + 'd/'+distro.id;
            dojo.place('<td><a href="'+distro_url+'">'+distro.name+'</a></td>', tr);
            dojo.place('<td>'+clue.relmgr.utils.format_date(distro.last_updated)+'</td>', tr);
            dojo.place('<td>'+distro.summary+'</td>', tr);
            dojo.place(tr, tbody);
        }));
    },

    _add_link: function(pager, text, page_num, search) {
        var a = dojo.place('<a class="page-link" href="'+this.base_url+'">'+text+'</a>', pager)
        dojo.connect(a, 'onclick', dojo.hitch({page_num: page_num, search: search, obj: this}, function(e) {
            e.preventDefault();
            query = {page_num: this.page_num};
            if (this.search)
                query.search = this.search;
            this.obj.update_listing(query);
        }));
        dojo.place('<span>&nbsp;</span>', pager);
    },

    setup_pager: function(pager, page_num, total_pages, search) {
        dojo.empty(pager);

        if (page_num > 1)
            this._add_link(pager, '&larr;', page_num-1, search);
        else
            dojo.place('<span class="page-link">&nbsp;</span>', pager);

        for (var i = 1; i < total_pages+1; i++) {
            if (i == page_num)
                dojo.place('<span class="page-link">'+i+'</span>', pager);
            else
                this._add_link(pager, ''+i, i, search);
            dojo.place('<span>&nbsp;</span>', pager);
        }

        if (page_num < total_pages)
            this._add_link(pager, '&rarr;', page_num+1, search);
        else
            dojo.place('<span class="page-link">&nbsp;</span>', pager);
    },

    _ensure_distro_listing_table: function() {
        var els = dojo.query('table.distro-listing');
        var table = null;
        if (els.length == 0) {
            dojo.query('.empty-list').forEach(function(x) {
                x.parentNode.removeChild(x);
            });

            var pagers = dojo.query('.pager');
            table = dojo.place('<table class="distro-listing">', pagers[0], 'after');
            var thead = dojo.place('<thead></thead>', table);
            var tr = dojo.place('<tr></tr>', thead);
            var th = dojo.place('<th class="distro-name">Name</th>', tr);
            th = dojo.place('<th class="distro-updated">Updated</th>', tr);
            th = dojo.place('<th class="distro-description">Description</th>', tr);
            var tbody = dojo.place('<tbody></tbody>', table);
        } else
            table = els[0];

        return table;
    },

    update_listing: function(query) {
        var url = new clue.relmgr.browser.URL(window.location.href);
        if (query) {
            url.comment_params = query;
            window.location.href = url.toString();
        }

        var table = this._ensure_distro_listing_table();

        dojo.addClass(table, 'inactive');

        var distro_group = this.distro_store.fetch({query: query}).results;

        // there will typically be 2 or more pagers on the same page (top and bottom)
        dojo.query('.pager').forEach(dojo.hitch(this, function(pager) {
            this.setup_pager(pager, distro_group.page_num, distro_group.total_pages, distro_group.search);
        }));

        this.populate_listing(distro_group.distros);
        if (distro_group.distros.length == 0) {
            dojo.place('<p class="empty-list">Sorry there are currently no items available (or you do not have access to any items).</p>', table, 'after');
            table.parentNode.removeChild(table);
        } else {
            dojo.removeClass(table, 'inactive');
        }

        var title_el = dojo.byId('page-title-header');
        var s = url.comment_params.search || url.query_params.search;
        if (s)
            title_el.innerHTML = 'Search Results for "'+s+'"';
        else
            title_el.innerHTML = 'Latest Updates';
    }
});
