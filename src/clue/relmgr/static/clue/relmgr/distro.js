dojo.provide('clue.relmgr.distro');
dojo.require('dojo.cookie');
dojo.require('dojox.data.JsonRestStore');
dojo.require('dijit.TooltipDialog');

clue.relmgr.distro.clear_node = function(node, callback) {
    var anim = dojo.fadeOut({node: node});
    dojo.connect(anim, 'onEnd', function(e) {
        node.innerHTML = '';
        if (callback)
            callback();
    });
    anim.play();
};

dojo.declare('clue.relmgr.distro.Distro', null, {
    constructor: function(base_url) {
        // summary:
        //     A class for controlling the user interface of a page viewing a distro.
        // base_url:
        //     main url for connecting for rpc/rest requests
        // description:
        //     Controls the various aspects of a page displaying information
        //     regarding a distribution.

        if (base_url != null & !base_url[-1] == '/')
            base_url = base_url + '/';
        this.base_url = base_url;
        this.indexmanager = new clue.relmgr.distro.IndexManager(base_url);
        dojo.connect(this.indexmanager, 'on_update', this, this.refresh_indexes);
        dojo.connect(this.indexmanager, 'on_delete', this, this.refresh_indexes);
    },

    activate: function() {
        dojo.addClass(dojo.body(), 'tundra');
        var blocks = dojo.query('.distro-indexes.can-modify');
        if (blocks.length > 0) {
            this._setup_modify_links(blocks[0]);
            this._setup_add_link(blocks[0]);
        }
    },

    refresh_indexes: function() {
        var index_root_store = new dojox.data.JsonRestStore({target: this.base_url+'i/'});
        var listing = dojo.query('.index-listing')[0];
        var blocks = dojo.query('.distro-indexes.can-modify');
        index_root_store.fetch({onComplete: dojo.hitch(this, function(res) {
            dojo.empty(listing);
            dojo.forEach(res.indexes, dojo.hitch(this, function(index) {
                var url = this.base_url + 'i/' + index;
                var li = dojo.place('<li></li>', listing);
                var link = dojo.place('<a href="'+url+'">'+index+'</a></li>', li);
                if (blocks.length > 0) {
                    this._setup_modify_link(link);
                }
            }));
        })});
    },

    _setup_add_link: function(block) {
        var header = dojo.query('h4', block)[0];
        var a = dojo.place('<a class="new-index" href="#">(add)</a>', header);
        dojo.connect(a, 'onclick', dojo.hitch(this, function(e) {
            e.preventDefault();
            this.show_new_index(e.target);
        }));
        dojo.place('<span id="index-manager-status" class="hidden"></span>', header);
    },

    _setup_modify_link: function(link) {
        var indexname = link.innerHTML;

        var div = dojo.place('<div class="index-actions"></div>', link, 'after');
        var modify_link = dojo.place('<a class="modify-index" href="#">modify</a>', div);
        var n = dojo.place('<span> - </span>', modify_link, 'after');
        var del_link = dojo.place('<a class="delete-index" href="#">delete</a>', n, 'after');

        dojo.connect(modify_link, 'onclick', dojo.hitch(this, function(e) {
            e.preventDefault();
            this.show_modify_index(e.target, indexname);
        }));

        dojo.connect(del_link, 'onclick', dojo.hitch(this, function(e) {
            e.preventDefault();
            this.show_del_index(e.target, indexname);
        }));
    },

    show_del_index: function(parentnode, indexname) {
        var dialog = dijit.byId('del_index');
        if (dialog == null) {
            dialog = new dijit.TooltipDialog({id: 'del_index',
                                              title: 'Delete Index?'});

            var fieldset = dojo.place('<fieldset><legend>Delete <em></em>?</legend></fieldset>',
                                      dialog.containerNode);

            var close = function() {
                dijit.popup.close(dialog);
            };

            dojo.place('<p>Are you sure you want to delete this index?</p>', fieldset);
            var buttons = dojo.place('<div class="buttons"></div>', fieldset);
            var del = dojo.place('<button id="save-del-index">Delete</button>', buttons);
            dojo.connect(del, 'onclick', dojo.hitch(this, function(e) {
                var em = dojo.query('fieldset legend em', dialog.containerNode)[0];
                var indexname = em.innerHTML;
                this.indexmanager.del_index(indexname);
                close();
            }));
            var cancel = dojo.place('<button id="cancel-del-index">Cancel</button>', buttons);
            dojo.connect(cancel, 'onclick', close);

            dojo.connect(dialog, "onBlur", close);
            dialog.startup();
        }

        dojo.query('fieldset legend em', dialog.containerNode).forEach(function(x) {
            x.innerHTML = indexname;
        });

        dijit.popup.open({parent: parentnode,
                          popup: dialog,
                          around: parentnode,
                          orient: {'BR':'TR', 'TR':'BR'},
                          onCancel: close});

    },

    _setup_modify_links: function(block) {
        dojo.query('li', block).forEach(dojo.hitch(this, function(x) {
            dojo.query('a', x).forEach(dojo.hitch(this, function(link) {
                if (dojo.hasClass(link, 'modify-index'))
                    return;
                this._setup_modify_link(link);
            }));
        }));
    },

    show_new_index: function(parentnode) {
        this._show_manage_index(parentnode);
    },

    show_modify_index: function(parentnode, indexname) {
        this._show_manage_index(parentnode, indexname);
    },

    _show_manage_index: function(parentnode, indexname) {
        var indexmanager = this.indexmanager;
        var close = function() {
            var dialog = dijit.byId('manage_index');
            dijit.popup.close(dialog);
        };

        var index_store = new dojox.data.JsonRestStore({target: this.base_url+'i/'+indexname});

        var dialog = dijit.byId('manage_index');
        var container = null;
        if (dialog == null) {
            dialog = new dijit.TooltipDialog({id: 'manage_index',
                                              title: 'Edit Index'});
            dojo.connect(dialog, "onBlur", close);
            container = dojo.place('<div id="index-manager-container" class="modify-indexes">', dialog.containerNode);

            var buttons = dojo.place('<div class="actions"></div>', dialog.containerNode);
            var save = dojo.place('<button id="save-modify-index">Save</button>', buttons);
            dojo.connect(save, 'onclick', function(x) {
                var inputs = dojo.query('.index-info input[name="indexname"]', container);
                if (inputs && inputs.length > 0) {
                    var input = inputs[0];
                    var value = input.value;
                    if (!value || value.length == 0)
                        alert('Please specify index name');
                    else
                        indexmanager.save_index(value);
                } else {
                    indexmanager.save_index(indexname);
                }

                close();
            });

            var cancel = dojo.place('<button id="cancel-modify-index">Cancel</button>', buttons);
            dojo.connect(cancel, 'onclick', close);

            dialog.startup();
        } else {
            container = dojo.byId('index-manager-container');
            dojo.empty(container);
        }

        dijit.popup.open({parent: parentnode,
                          popup: dialog,
                          around: parentnode,
                          orient: {'BR':'TR', 'TR':'BR'},
                          onCancel: close});

        dojo.attr(dojo.byId('save-modify-index'), 'disabled', true);

        var distro_store = new dojox.data.JsonRestStore({target: this.base_url + '../'});
        dojo.empty(container);

        /* setup new add-index-entry form stuff */
        var addnew = dojo.place('<fieldset id="new-index-entry"><legend>Add New Requirement</legend></fieldset>', container);
        var form = dojo.place('<form></form>', addnew);
        var resdiv = dojo.place('<div class="index-editing-distro-list"></div>', addnew);
        dojo.connect(form, 'onsubmit', dojo.hitch(this, function(e) {
            e.preventDefault();
            var obj = dojo.formToObject(form);
            dojo.cookie('lastsearch', obj.req, {expires: 30});
            distro_store.fetch({
                query: {req: obj.req},
                onComplete: function(res) {
                    dojo.forEach(res.distros, function(distro) {
                        if (distro.files == null || distro.files.length == 0)
                            return;
                        dojo.place('<div class="distro">'+distro.name+'</div>', resdiv);
                        dojo.forEach(distro.files, function(file) {
                            var n = dojo.place('<div class="file"></div>', resdiv);
                            var input = dojo.place('<input class="checkbox" type="checkbox" name="'+distro.name+'" value="'+file.version+'">', n);
                            dojo.connect(input, 'onchange', function(e) {
                                if (e.target.checked)
                                    indexmanager.show_new_index_entry({name: distro.name, req: distro.name+'=='+file.version});
                                else
                                    indexmanager.clear_index_entry(distro.name);
                            });
                            var a = dojo.place('<a href="'+file.url+'">'+file.version+'</a>', n);
                            dojo.connect(a, 'onclick', function(e) {
                                e.preventDefault();
                                if (input.checked)
                                    indexmanager.clear_index_entry(distro.name);
                                else
                                    indexmanager.show_new_index_entry({name: distro.name, req: distro.name+'=='+file.version});
                            });
                        });
                    });
                }});
        }));

        var reqin = dojo.place('<input type="text" name="req">', form);
        var lastsearch = dojo.cookie('lastsearch');
        if (lastsearch != null)
            dojo.attr(reqin, 'value', lastsearch);
        dojo.place('<input type="submit" value="Find">', form);

        var dl = dojo.place('<dl class="index-info"><dt>Index Name:</dt></dl>', container, 'first');
        var dd = dojo.place('<dd class="indexname"></dd>', dl);
        if (indexname) {
            dojo.place('<input type="hidden" name="indexname" value="'+indexname+'">'+indexname, dd);
            index_store.fetch({onComplete: function(res) {
                indexmanager.setup_current_index_entries(res.entries);
            }});
        } else {
            dojo.place('<input type="text" name="indexname">', dd);
            indexmanager.setup_current_index_entries();
        }
    }

});

dojo.declare('clue.relmgr.distro.IndexManager', null, {
    constructor: function(base_url) {
        if (base_url != null & !base_url[-1] == '/')
            base_url = base_url + '/';
        this.base_url = base_url;

        this.index_root_store = new dojox.data.JsonRestStore({target: this.base_url+'i/'});
    },

    set_status: function(s, class_) {
        var status = dojo.byId('index-manager-status');
        if (s) {
            var span = dojo.create('span', {innerHTML: s});
            if (class_)
                dojo.addClass(span, class_);
            dojo.place(span, status);
            dojo.style(status, "opacity", "1");
            dojo.removeClass(status, 'hidden');
        } else
            clue.relmgr.distro.clear_node(status, function() {dojo.addClass(status, 'hidden')});
    },

    show_new_index_entry: function(index) {
        var block = dojo.byId('current-index-entries');
        if (dojo.query('.target', block).length > 0) {
            if (dojo.query('.target input[name="'+index.name+'"]', block).length > 0)
                return;
            dojo.place('<span>, </span>', block);
        } else {
            dojo.query('.empty', block).forEach(function(x) {
                x.parentNode.removeChild(x);
            });
        }
        var span = dojo.place('<span class="target">'+index.name+'</span>', block);
        var link = dojo.place('<a class="delete" href="#">x</a>', span);
        var input = dojo.place('<input type="hidden" name="'+index.name+'" value="'+index.req+'">', span);
        dojo.connect(link, 'onclick', dojo.hitch(this, function(e) {
            e.preventDefault();
            this.clear_index_entry(index.name);
        }));

        var container = dojo.byId('index-manager-container');
        dojo.query('input.checkbox[name="'+index.name+'"]', container).forEach(function(x) {
            dojo.attr(x, 'checked', true);
        });

        dojo.attr(dojo.byId('save-modify-index'), 'disabled', false);
    },

    clear_index_entry: function(indexname) {
        var block = dojo.byId('current-index-entries');
        dojo.query('.target input[name="'+indexname+'"]', block).forEach(function(x) {
            var target = x.parentNode;
            target.parentNode.removeChild(target);
        });
    },

    del_index: function(indexname) {
        this.set_status('Deleting...', 'loading');
        _del = dojo.hitch(this, function(index) {
            this.index_root_store.deleteItem(index);
            this.index_root_store.save({onComplete: dojo.hitch(this, function() {
                this.set_status();
                this.on_delete(index);
            })});
        });

        this.index_root_store.fetch({query: '?indexname='+indexname,
                                     onComplete: dojo.hitch(this, function(res) {
                                         _del(res.indexes[0]);
                                     })});
    },

    save_index: function(indexname) {
        this.set_status('Saving...', 'loading');
        dojo.attr(dojo.byId('save-modify-index'), 'disabled', true);

        var entries = new Array();
        dojo.query('#current-index-entries .target input').forEach(function(x) {
            entries.push(x.value);
        });

        var _save = dojo.hitch(this, function(indexname, entries, index) {
            if (index != null) {
                this.index_root_store.changing(index);
            } else {
                var Index = this.index_root_store.getConstructor();
                index = new Index();
                index.indexname = indexname;
            }
            index.entries = entries;
            this.index_root_store.save({onComplete: dojo.hitch(this, function(x) {
                this.on_update(index);
                this.set_status();
            })});
        });

        this.index_root_store.fetch({query: '?indexname='+indexname,
                                     onComplete: dojo.hitch(this, function(res) {
                                         _save(indexname, entries, res.indexes[0]);
                                     })});
    },

    on_update: function(item) {
    },

    on_delete: function(item) {
    },

    setup_current_index_entries: function(entries) {
        var container = dojo.byId('index-manager-container');
        var first = dojo.query('.index-info', container)[0];
        var current_indexes_block = dojo.place('<fieldset id="current-index-entries"></fieldset>',
                                               first, 'after');
        dojo.place('<legend>Distro Reqs</legend>', current_indexes_block);

        if (entries)
            dojo.forEach(entries, dojo.hitch(this, this.show_new_index_entry));

        if (!entries || entries.length == 0)
            dojo.place('<span class="empty">empty</span>', current_indexes_block);
    }

});
