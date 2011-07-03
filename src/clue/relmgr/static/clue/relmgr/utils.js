dojo.provide('clue.relmgr.utils')

clue.relmgr.utils.months = ['Jan', 'Feb', 'Mar', 'Apr', 'May',
                            'Jun', 'Jul', 'Sep', 'Oct', 'Nov', 'Dec'];


clue.relmgr.utils.parse_int = function(s) {
    // Slightly smarter pasreInt that knows how to remove leading zeroes
    var new_s = s.replace(/^[0]+/g, '');
    return parseInt(new_s);
};

clue.relmgr.utils.parse_date = function(s) {
    // expects iso formatted date/time such as:
    // 2009-03-24T11:32:16

    var parse_int = clue.relmgr.utils.parse_int;
    var parts = s.split('T');
    var dateparts = parts[0].split('-');
    var timeparts = parts[1].split(':');

    var dt = new Date(parse_int(dateparts[0]), parse_int(dateparts[1]), parse_int(dateparts[2]),
                      parse_int(timeparts[0]), parse_int(timeparts[1]), parse_int(timeparts[2]));
    return dt;
};

clue.relmgr.utils.format_date = function(dt) {
    if (!dt)
        return 'N/A';
    
    if (dt instanceof String || typeof(dt) == 'string')
        dt = clue.relmgr.utils.parse_date(dt);

    date = ''+dt.getDate();
    if (date.length == 1)
        date = '0'+date.length;

    var month = clue.relmgr.utils.months[(dt.getMonth()-1)];
    // returns string of format Jan-23-2008
    return month + '-' + date + '-' + dt.getFullYear()
};

clue.relmgr.utils.is_empty = function(obj) {
    for (var x in obj) {
        if (obj.hasOwnProperty(x))
            return false;
    }
    return true;
}
