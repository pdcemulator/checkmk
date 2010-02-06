import check_mk, livestatus, htmllib, time
from lib import *

multisite_datasources = {}
multisite_filters     = {}
multisite_layouts     = {}
multisite_painters    = {}
multisite_sorters = {}

max_display_columns   = 10
max_group_columns     = 3
max_sort_columns      = 4


def setup(h):
    global html
    html = h

    if check_mk.multiadmin_restrict and \
	html.req.user not in check_mk.multiadmin_unrestricted_users:
	    auth_user = html.req.user
    else:
	auth_user = None

    connect_to_livestatus(html, auth_user)

def page(h):
    setup(h)
    html.header("Experimental")
    # show_page("hosts", "ungrouped_list", [ "sitename_plain", "host_with_state" ])
    show_page("services",  # data source
	      [ "host", "service", "svcstate" ], # filters
	      "grouped_list", # layout
	      [ "site", "host_name" ], # grouping columns
	      [ "site_icon", "host_black" ], # group painters
	      [ "service_state", "service_description", "state_age", "plugin_output" ])

    html.footer()

def page_designer(h):
    setup(h)
    html.header("Experimental: View designer")
    html.begin_form("view")
    html.write("<table class=view>\n")
    def show_list(name, title, data):
	html.write("<tr><td class=legend>%s</td>" % title)
	html.write("<td class=content>")
	html.select(name, [ (k, v["title"]) for k,v in data.items() ])
	html.write("</td></tr>\n")

    # [1] Datasource
    show_list("datasource", "1. Datasource", multisite_datasources)
    
    # [2] Layout
    show_list("layout", "2. Layout", multisite_layouts)
  
    # [3] Filters 
    html.write("<tr><td class=legend>3. Filters</td><td>")
    html.write("<table class=filters>")
    html.write("<tr><th>Filter</th><th>usage</th><th>hardcoded settings</th></tr>\n")
    for fname, filt in multisite_filters.items():
	html.write("<tr>")
	html.write("<td>%s</td>" % filt.title)
	html.write("<td>")
	html.select("filter_%s" % fname, [("off", "Don't use"), ("show", "Show to user"), ("hard", "Hardcode")])
	html.write("</td><td>")
	filt.display()
	html.write("</td></tr>\n")
    html.write("</table></td></tr>\n")
   
    # [4] Sorting
    def column_selection(title, var_prefix, maxnum, data, order=False):
	html.write("<tr><td class=legend>%s</td><td class=content>" % title)
	for n in range(1, maxnum+1):
	    collist = [ ("", "") ] + [ (name, p["title"]) for name, p in data.items() ]
	    html.write("%02d " % n)
	    html.select("%s%d" % (var_prefix, n), collist)
	    if order:
		html.write(" ")
		html.select("%sorder_%d" % (var_prefix, n), [("asc", "Ascending"), ("dsc", "Descending")])
	    html.write("<br />")
	html.write("</td></tr>\n")
    column_selection("4. Sorting", "sort_", max_sort_columns, multisite_sorters, True)

    # [5] Grouping
    column_selection("5. Group by", "group_", max_group_columns, multisite_painters)

    # [6] Columns (painters)	
    column_selection("6. Display columns", "col_", max_display_columns, multisite_painters)


    html.write("<tr><td colspan=2>")
    html.button("show", "Try out")
    html.write("</table>\n")

    if html.has_var("show") or html.has_var("filled_in"):
	preview_view()

def preview_view():
    datasourcename = html.var("datasource")
    datasource = multisite_datasources[datasourcename]
    tablename = datasource["table"]
    layoutname = html.var("layout")
    filternames = []
    add_headers = ""
    for fname, filt in multisite_filters.items():
	usage = html.var("filter_%s" % fname)
	if usage == "show":
	    filternames.append(fname)
	elif usage == "hard":
	    add_headers += filt.filter(tablename)

    sorternames = []
    for n in range(1, max_sort_columns+1):
	sname = html.var("sort_%d" % n)
	if sname:
	    reverse = html.var("sort_order_%d" % n) == "dsc"
	    sorternames.append((sname, reverse))

    group_painternames = [] 
    for n in range(1, max_group_columns+1):
	pname = html.var("group_%d" % n)
	if pname:
	    group_painternames.append(pname)

    painternames = []
    for n in range(1, max_display_columns+1):
	pname = html.var("col_%d" % n)
	if pname:
	    painternames.append(pname)
   
    html.set_var("filled_in", "on") 
    show_page(datasourcename, add_headers, filternames, layoutname, group_painternames, painternames, sorternames)


def show_page(datasourcename, add_headers, filternames, layoutname, group_painternames, painternames, sorternames):
    datasource = multisite_datasources[datasourcename]
    tablename = datasource["table"]
    filters = [ multisite_filters[fn] for fn in filternames ]
    filterheaders = "".join(f.filter(tablename) for f in filters)
    query = filterheaders + add_headers
    data = query_data(datasource, query)
    sorters = [ (multisite_sorters[sn], reverse) for sn, reverse in sorternames ]
    sort_data(data[2], sorters, tablename)
    painters = [ multisite_painters[n] for n in painternames ]
    layout = multisite_layouts[layoutname]
    group_painters = [ multisite_painters[n] for n in group_painternames ]
    group_columns = needed_group_columns(group_painters, tablename)
    layout["render"](data, filters, group_columns, group_painters, painters)

def needed_group_columns(painters, tablename):
    columns = []
    for p in painters:
	t = p.get("table", tablename)
	if tablename != t:
	    prefix = p["table"][:-1] + "_"
	else:
	    prefix = ""
	for c in p["columns"]:
	    if c != "site":
		c = prefix + c
	    if c not in columns:
		columns.append(c)
    return columns


def show_filter_form(filters):
    if len(filters) > 0:
	html.begin_form("filter")
	html.write("<table class=form id=filter>\n")
	for f in filters:
	    html.write("<tr><td class=legend>%s</td>" % f.title)
	    html.write("<td class=content>")
	    f.display()
	    html.write("</td></tr>\n")
	html.write("<tr><td class=legend></td><td class=content>")
	html.button("search", "Search", "submit")
	html.write("</td></tr>\n")
	html.write("</table>\n")
	html.end_form()

def query_data(datasource, add_headers):
    tablename = datasource["table"]
    query = "GET %s\n" % tablename
    columns = datasource["columns"]
    query += "Columns: %s\n" % " ".join(datasource["columns"])
    query += add_headers
    live.set_prepend_site(True)
    data = live.query(query)
    columns_with_site = ["site"] + columns
    assoc = [ dict(zip(columns_with_site, row)) for row in data ]
    live.set_prepend_site(False)

    # If you understand this code than you are really smart >;-/
    def rowfunction(painter, row):
	paintertable = painter.get("table")
	if paintertable in [None, tablename]:
	    return lambda x: row[x]
	else:
	    return lambda x: row.get(paintertable[:-1] + "_" + x, row.get(x))

    return (["site"] + columns, rowfunction, assoc)

def sort_data(data, sorters, tablename):
    if len(sorters) == 0:
	return
    
    # Construct sort function. It must return -1, 0 or +1 when
    # comparing to elements of data. The sorter functions do
    # not expect a row array but a rowfunction for each of the
    # the elements
    sort_cmps = []

    # convert compare function that gets to functions row() into
    # compare function that gets to row-dictionaries. Also take
    # reverse sorting into account
    def make_compfunc(rowfunc, compfunc, reverse):
        if reverse:	
	    return lambda dict2, dict1: compfunc(lambda k: rowfunc(dict1, k), lambda k: rowfunc(dict2, k))
	else:
	    return lambda dict1, dict2: compfunc(lambda k: rowfunc(dict1, k), lambda k: rowfunc(dict2, k))

    for s, reverse in sorters:
        tn = s.get("table", tablename)
	if tn == tablename:
	    rowfunc = lambda a, b: a[b]
	else:
	    prefix = tn[:-1] + "_"
	    rowfunc = lambda a, b: a[prefix + b]

	compfunc = s["cmp"]
	cmp = make_compfunc(rowfunc, compfunc, reverse)
	sort_cmps.append(cmp)

    compfunc = None

    def multisort(e1, e2):
	for cmp in sort_cmps:
	    c = cmp(e1, e2)
	    if c != 0: return c
	return 0 # equal

    if len(sort_cmps) > 1:
	data.sort(multisort)
    else:
	data.sort(sort_cmps[0])
    
     
def connect_to_livestatus(html, auth_user = None):
    global site_status, live
    site_status = {}
    # If there is only one site (non-multisite), than
    # user cannot enable/disable. 
    if check_mk.is_multisite():
	enabled_sites = {}
	for sitename, site in check_mk.sites().items():
	    varname = "siteoff_" + sitename
	    if not html.var(varname) == "on":
		enabled_sites[sitename] = site
	global live
	live = livestatus.MultiSiteConnection(enabled_sites)
	live.set_prepend_site(True)
        for site, v1, v2 in live.query("GET status\nColumns: livestatus_version program_version"):
	    site_status[site] = { "livestatus_version": v1, "program_version" : v2 }
	live.set_prepend_site(False)
    else:
	live = livestatus.SingleSiteConnection(check_mk.livestatus_unix_socket)

    if auth_user:
	live.addHeader("AuthUser: %s" % auth_user)

##################################################################################
# Data sources
##################################################################################

multisite_datasources["hosts"] = {
    "title"   : "All hosts",
    "table"   : "hosts",
    "columns" : ["name", "state"],
}

multisite_datasources["services"] = {
    "title"   : "All services",
    "table"   : "services",
    "columns" : ["description", "plugin_output", "state", "has_been_checked", 
                 "host_name", "host_state", "last_state_change" ],
}

##################################################################################
# Filters
##################################################################################

def declare_filter(f):
    multisite_filters[f.name] = f

class Filter:
    def __init__(self, name, title, table, columns, htmlvars):
	self.name = name
	self.table = table
	self.title = title
	self.columns = columns
	self.htmlvars = htmlvars
	
    def display(self):
	raise MKInternalError("Incomplete implementation of filter %s '%s': missing display()" % \
		(self.name, self.title))
	html.write("FILTER NOT IMPLEMENTED")

    def filter(self):
	raise MKInternalError("Incomplete implementation of filter %s '%s': missing filter()" % \
	    (self.name, self.title))
	html.write("FILTER NOT IMPLEMENTED")

    def tableprefix(self, tablename):
	if self.table == tablename:
	    return ""
	else:
	    return self.table[:-1] + "_"

class FilterText(Filter):
    def __init__(self, name, title, table, column, htmlvar, op):
	Filter.__init__(self, name, title, table, [column], [htmlvar])
	self.op = op
    
    def display(self):
	htmlvar = self.htmlvars[0]
	current_value = html.var(htmlvar, "")
	html.text_input(htmlvar, current_value)

    def filter(self, tablename):
	htmlvar = self.htmlvars[0]
	current_value = html.var(htmlvar)
	if current_value:
	    return "Filter: %s%s %s %s\n" % (self.tableprefix(tablename), self.columns[0], self.op, current_value)
	else:
	    return ""

class FilterServiceState(Filter):
    def __init__(self):
	Filter.__init__(self, "svcstate", "Service states", 
		"services", [ "state", "has_been_checked" ], [ "st0", "st1", "st2", "st3", "stp" ])
    
    def display(self):
	if html.var("filled_in"):
	    defval = ""
	else:
	    defval = "on"
	for var, text in [("st0", "OK"), ("st1", "WARN"), ("st2", "CRIT"), ("st3", "UNKNOWN"), ("stp", "PENDING")]:
	    html.checkbox(var, defval)
	    html.write(" %s " % text)

    def filter(self, tablename):
	headers = []
	if html.var("filled_in"):
	    defval = ""
	else:
	    defval = "on"

	for i in [0,1,2,3]:
	    if html.var("st%d" % i, defval) == "on":
		headers.append("Filter: %sstate = %d\nFilter: has_been_checked = 1\nAnd: 2\n" % (self.tableprefix(tablename), i))
	if html.var("stp", defval) == "on":
	    headers.append("Filter: has_been_checked = 0\n")
	if len(headers) == 0:
	    return "Limit: 0\n" # now allowed state
	else:
	    return "".join(headers) + ("Or: %d\n" % len(headers))

declare_filter(FilterText("host", "Hostname", "hosts", "name", "host", "~~"))
declare_filter(FilterText("service", "Service", "services", "description", "service", "~~"))
declare_filter(FilterServiceState())

##################################################################################
# Sorting
##################################################################################

# return -1, if r1 < r2, 0 if they are equal, 1 otherwise
def cmp_atoms(s1, s2):
    if s1 < s2:
        return -1
    elif s1 == s2:
        return 0
    else:
        return 1

def cmp_state_equiv(r):
    if r("has_been_checked") == 0:
	return -1
    s = r("state")
    if s <= 1:
	return s
    else:
	return 5 - s # swap crit and unknown

def cmp_svc_states(r1, r2):
    return cmp_atoms(cmp_state_equiv(r1), cmp_state_equiv(r2))
   
def cmp_simple_string(column, r1, r2):
    return cmp_atoms(r1(column).lower(), r2(column).lower())
    
def cmp_simple_number(column, r1, r2):
    return cmp_atoms(r1(column), r2(column))
    
multisite_sorters["svcstate"] = {
    "title"   : "Service state",
    "table"   : "services",
    "columns" : ["state", "has_been_checked"],
    "cmp"     : cmp_svc_states
}

def declare_simple_sorter(name, title, table, column, func):
    multisite_sorters[name] = {
	"title"   : title,
	"table"   : table,
	"columns" : [ column ],
        "cmp"     : lambda r1, r2: func(column, r1, r2)
    }

declare_simple_sorter("host",      "Hostname",              "hosts",    "name",          cmp_simple_string)
declare_simple_sorter("svcdescr",  "Service description",   "services", "description",   cmp_simple_string)
declare_simple_sorter("svcoutput", "Service plugin output", "services", "plugin_output", cmp_simple_string)

##################################################################################
# Layouts
##################################################################################

def render_ungrouped_list(data, filters, group_columns, group_painters, painters):
    show_filter_form(filters)
    columns, rowfunction, rows = data
    html.write("<table class=services>\n")
    trclass = None
    for row in rows:
        if trclass == "odd":
	    trclass = "even"
	else:
	    trclass = "odd"
        # render state, if available through whole tr
	state = row.get("state", 0)
	html.write("<tr class=%s%d>" % (trclass, state))
        for p in painters:
	    html.write(p["paint"](rowfunction(p, row)))
	html.write("</tr>\n")
    html.write("<table>\n")

def render_grouped_list(data, filters, group_columns, group_painters, painters):
    show_filter_form(filters)
    columns, rowfunction, rows = data
    html.write("<table class=services>\n")
    last_group = None
    trclass = None
    for row in rows:
        if trclass == "odd":
	    trclass = "even"
	else:
	    trclass = "odd"

        this_group = [ row[c] for c in group_columns ]
	if this_group != last_group:
	    html.write("<tr class=groupheader>")
	    html.write("<td colspan=%d><table><tr>" % len(painters))
            for p in group_painters:
	        html.write(p["paint"](rowfunction(p, row)))
	    html.write("</tr></table></td></tr>\n")
	    last_group = this_group
	    trclass = "even"
        # render state, if available through whole tr
	state = row.get("state", 0)
	html.write("<tr class=%s%d>" % (trclass, state))
        for p in painters:
	    html.write(p["paint"](rowfunction(p, row)))
	html.write("</tr>\n")
    html.write("<table>\n")

multisite_layouts["ungrouped_list"] = { 
    "title"  : "Ungrouped list",
    "render" : render_ungrouped_list,
}

multisite_layouts["grouped_list"] = { 
    "title"  : "Grouped list",
    "render" : render_grouped_list,
    "group" : True
}

##################################################################################
# Painters
##################################################################################
def nagios_host_url(sitename, host):
    nagurl = check_mk.site(sitename)["nagios_cgi_url"]
    return nagurl + "/status.cgi?host=" + htmllib.urlencode(host)

def nagios_service_url(sitename, host, svc):
    nagurl = check_mk.site(sitename)["nagios_cgi_url"]
    return nagurl + ( "/extinfo.cgi?type=2&host=%s&service=%s" % (htmllib.urlencode(host), htmllib.urlencode(svc)))

def paint_plain(text):
    return "<td>%s</td>" % text

def paint_age(timestamp, has_been_checked):
    if not has_been_checked:
	return "<td class=age>-</td>"
	   
    age = time.time() - timestamp
    if age < 60 * 10:
	age_class = "agerecent"
    else:
	age_class = "age"
    return "<td class=%s>%s</td>\n" % (age_class, html.age_text(age))

def paint_site_icon(row):
    if row("site") and check_mk.multiadmin_use_siteicons:
	return "<td><img class=siteicon src=\"icons/site-%s-24.png\"> " % row("site")
    else:
	return "<td></td>"
	

multisite_painters["sitename_plain"] = {
    "title" : "The id of the site",
    "columns" : ["site"],
    "paint" : lambda row: "<td>%s</td>" % row("site"),
}

def paint_host_black(row):
    state = row("state")
    if state == 0:
	style = "up"
    else:
	style = "down"
    return "<td class=host><b class=%s><a href=\"%s\">%s</a></b></td>" % \
	(style, nagios_host_url(row("site"), row("name")), row("name"))

multisite_painters["host_black"] = {
    "title" : "Hostname, red background if down or unreachable",
    "columns" : ["site","name"],
    "table" : "hosts",
    "paint" : paint_host_black,
}

multisite_painters["host_with_state"] = {
    "title" : "Hostname colored with state",
    "columns" : ["site","name"],
    "table" : "hosts",
    "paint" : lambda row: "<td class=hstate%d><a href=\"%s\">%s</a></td>" % \
	(row("state"), nagios_host_url(row("site"), row("name")), row("name")),
}

def paint_service_state_short(row):
    if row("has_been_checked") == 1:
	state = row("state")
	name = nagios_short_state_names[row("state")]
    else:
	state = "p"
	name = "PEND"
    return "<td class=state%s>%s</td>" % (state, name)

multisite_painters["service_state"] = {
    "title" : "The service state, colored and short (4 letters)",
    "columns" : ["has_been_checked","state"],
    "paint" : paint_service_state_short
}

multisite_painters["site_icon"] = {
    "title" : "Icon showing the site",
    "columns" : ["site"],
    "paint" : paint_site_icon
}

multisite_painters["plugin_output"] = {
    "title" : "Output of check plugin",
    "columns" : ["plugin_output"],
    "paint" : lambda row: paint_plain(row("plugin_output"))
}
    
multisite_painters["service_description"] = {
    "title" : "Service description",
    "columns" : ["description"],
    "paint" : lambda row: "<td><a href=\"%s\">%s</a></td>" % (nagios_service_url(row("site"), row("host_name"), row("description")), row("description"))
}

multisite_painters["state_age"] = {
    "title" : "The age of the current state",
    "columns" : [ "has_been_checked", "last_state_change" ],
    "paint" : lambda row: paint_age(row("last_state_change"), row("has_been_checked") == 1)
}
