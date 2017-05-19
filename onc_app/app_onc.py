from flask import Flask, render_template, request, redirect, make_response, url_for
app_onc = Flask(__name__)

import astrodbkit
from astrodbkit import astrodb
import os
import sys
from io import StringIO
from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.models import ColumnDataSource, HoverTool, OpenURL, TapTool
from bokeh.models.widgets import Panel, Tabs
from ONCdb import make_onc
from astropy import units as u
from astropy.coordinates import SkyCoord
from astroquery.simbad import Simbad
import pandas as pd
from collections import OrderedDict
from math import sqrt
import numpy as np

app_onc.vars = dict()
app_onc.vars['query'] = ''
app_onc.vars['search'] = ''
app_onc.vars['specid'] = ''
app_onc.vars['source_id'] = ''

db_file = os.path.join(os.path.dirname(make_onc.__file__),'orion.db')
pd.set_option('max_colwidth', 150)

# Redirect to the main page
@app_onc.route('/')
@app_onc.route('/index')
@app_onc.route('/index.html')
@app_onc.route('/query.html')
def onc_home():
    return redirect('/query')

# Page with a text box to take the SQL query
@app_onc.route('/query', methods=['GET', 'POST'])
def onc_query():
    defquery = 'SELECT * FROM sources'
    if app_onc.vars['query']=='':
        app_onc.vars['query'] = defquery

    return render_template('query.html', defquery=app_onc.vars['query'],
                           defsearch=app_onc.vars['search'], specid=app_onc.vars['specid'],
                           source_id=app_onc.vars['source_id'], version=astrodbkit.__version__)

# @app_onc.route('/selection', methods=['POST','GET'])
# def onc_selection():
#     # Create query from selection
#     ids = list(filter(None,[request.form.get(str(n)) for n in range(5)]))
#     q = 'SELECT * FROM sources WHERE id in ({})'.format(','.join(ids))
#     print(q)
#
#     return render_template('view_search.html', table=data.to_html(classes='display', index=False).replace('&lt;','<').replace('&gt;','>'), query=app_onc.vars['query'],
#                             script=script, plot=div, warning=warning_message)

# Grab results of query and display them
@app_onc.route('/runquery', methods=['POST','GET'])
def onc_runquery():
    db = astrodb.Database(db_file)
    app_onc.vars['query'] = request.form['query_to_run']
    htmltxt = app_onc.vars['query'].replace('<', '&lt;')

    # Only SELECT commands are allowed
    if not app_onc.vars['query'].lower().startswith('select'):
        return render_template('error.html', headermessage='Error in Query',
                               errmess='<p>Only SELECT queries are allowed. You typed:</p><p>'+htmltxt+'</p>')

    # Run the query
    stdout = sys.stdout  # Keep a handle on the real standard output
    sys.stdout = mystdout = StringIO()  # Choose a file-like object to write to
    try:
        t = db.query(app_onc.vars['query'], fmt='table', use_converters=False)
    except ValueError:
        t = db.query(app_onc.vars['query'], fmt='array', use_converters=False)
    except:
        return render_template('error.html', headermessage='Error in Query',
                               errmess='<p>Error in query:</p><p>'+htmltxt+'</p>')
    sys.stdout = stdout

    # Check for any errors from mystdout
    if mystdout.getvalue().lower().startswith('could not execute'):
        return render_template('error.html', headermessage='Error in Query',
                               errmess='<p>Error in query:</p><p>'+mystdout.getvalue().replace('<', '&lt;')+'</p>')

    # Check how many results were found
    if type(t)==type(None):
        return render_template('error.html', headermessage='No Results Found',
                               errmess='<p>No entries found for query:</p><p>' + htmltxt +
                                       '</p><p>'+mystdout.getvalue().replace('<', '&lt;')+'</p>')

    # Convert to Pandas data frame
    try:
        data = t.to_pandas()
    except AttributeError:
        return render_template('error.html', headermessage='Error in Query',
                               errmess='<p>Error for query:</p><p>'+htmltxt+'</p>')

    # Create checkbox first column
    buttonlist = []
    for index, row in data.iterrows():
        button = '<input type="checkbox" name="{}" value="{}">'.format(str(index),repr(list(row)))
        buttonlist.append(button)
    data['Select'] = buttonlist
    cols = data.columns.tolist()
    cols.pop(cols.index('Select'))
    data = data[['Select']+cols]

    try:
        script, div, warning_message = onc_skyplot(t)
    except:
        script = div = warning_message = ''

    return render_template('view_search.html', table=data.to_html(classes='display', index=False).replace('&lt;','<').replace('&gt;','>'), query=app_onc.vars['query'],
                            script=script, plot=div, warning=warning_message)


@app_onc.route('/export', methods=['POST'])
def onc_export():
    
    # Get all the checked rows
    checked = request.form
    results = []
    for k in sorted(checked):
        if k.isdigit():
            results.append(eval(checked[k]))
    
    # Mkae an array to export
    results = np.array(results, dtype=str)
    filename = 'results.txt'
    np.savetxt(filename, results, delimiter='|', fmt='%s')
    
    with open(filename, 'r') as f:
        file_as_string = f.read()
    os.remove(filename)  # Delete the file after it's read

    response = make_response(str(file_as_string))
    response.headers["Content-type"] = 'text; charset=utf-8'
    response.headers["Content-Disposition"] = "attachment; filename={}".format(filename)
    return response

# Perform a search
@app_onc.route('/search', methods=['POST'])
def onc_search():
    db = astrodb.Database(db_file)
    app_onc.vars['search'] = request.form['search_to_run']
    search_table = 'sources'
    search_value = app_onc.vars['search']

    # Process search
    search_value = search_value.replace(',', ' ').split()
    if len(search_value) == 1:
        search_value = search_value[0]
    else:
        try:
            search_value = [float(s) for s in search_value]
        except:
            return render_template('error.html', headermessage='Error in Search',
                                   errmess='<p>Could not process search input:</p>' +
                                           '<p>' + app_onc.vars['search'] + '</p>')

    # Run the search
    stdout = sys.stdout  # Keep a handle on the real standard output
    sys.stdout = mystdout = StringIO()  # Choose a file-like object to write to
    
    # Get table of results
    t = db.search(search_value, search_table, fetch=True)
    sys.stdout = stdout

    try:
        data = t.to_pandas()
    except AttributeError:
        return render_template('error.html', headermessage='Error in Search',
                               errmess=mystdout.getvalue().replace('<', '&lt;'))
                               
    # Create checkbox first column
    buttonlist = []
    for index, row in data.iterrows():
        button = '<input type="checkbox" name="{}" value="{}">'.format(str(index),repr(list(row)))
        buttonlist.append(button)
    data['Select'] = buttonlist
    cols = data.columns.tolist()
    cols.pop(cols.index('Select'))
    data = data[['Select']+cols]

    script, div, warning_message = onc_skyplot(t)

    return render_template('view_search.html', table=data.to_html(classes='display', index=False).replace('&lt;','<').replace('&gt;','>'), query=search_value,
                            script=script, plot=div, warning=warning_message)


# # Plot a spectrum
# @app_onc.route('/spectrum', methods=['POST'])
# def onc_plot():
#     db = astrodb.Database(db_file)
#     app_onc.vars['specid'] = request.form['spectrum_to_plot']
#
#     # If not a number, error
#     if not app_onc.vars['specid'].isdigit():
#         return render_template('error.html', headermessage='Error in Input',
#                                errmess='<p>Input was not a number.</p>')
#
#     # Grab the spectrum
#     stdout = sys.stdout  # Keep a handle on the real standard output
#     sys.stdout = mystdout = StringIO()  # Choose a file-like object to write to
#     query = 'SELECT spectrum, flux_units, wavelength_units, source_id, instrument_id, telescope_id ' + \
#             'FROM spectra WHERE id=' + app_onc.vars['specid']
#     t = db.query(query, fetch='one', fmt='dict')
#     sys.stdout = stdout
#
#     # Check for errors first
#     if mystdout.getvalue().lower().startswith('could not execute'):
#         return render_template('error.html', headermessage='Error in Query',
#                                errmess='<p>Error in query:</p><p>'+mystdout.getvalue().replace('<', '&lt;')+'</p>')
#
#     # Check if found anything
#     if isinstance(t, type(None)):
#         return render_template('error.html', headermessage='No Result', errmess='<p>No spectrum found.</p>')
#
#     spec = t['spectrum']
#
#     query = 'SELECT shortname FROM sources WHERE id='+str(t['source_id'])
#     shortname = db.query(query, fetch='one', fmt='dict')['shortname']
#
#     # Make the plot
#     tools = "resize,crosshair,pan,wheel_zoom,box_zoom,reset"
#
#     # create a new plot
#     wav = 'Wavelength ('+t['wavelength_units']+')'
#     flux = 'Flux ('+t['flux_units']+')'
#     # can specify plot_width if needed
#     p = figure(tools=tools, title=shortname, x_axis_label=wav, y_axis_label=flux, plot_width=800)
#
#     p.line(spec.data[0], spec.data[1], line_width=2)
#
#     script, div = components(p)
#
#     return render_template('spectrum.html', script=script, plot=div)


# Check inventory
@app_onc.route('/inventory', methods=['POST'])
@app_onc.route('/inventory/<int:source_id>')
def onc_inventory(source_id=None):
    db = astrodb.Database(db_file)
    if source_id is None:
        app_onc.vars['source_id'] = request.form['id_to_check']
        path = ''
    else:
        app_onc.vars['source_id'] = source_id
        path = '../'
    
    # Grab inventory
    stdout = sys.stdout
    sys.stdout = mystdout = StringIO()
    t = db.inventory(app_onc.vars['source_id'], fetch=True, fmt='table')
    sys.stdout = stdout

    # Check for errors (no results)
    if mystdout.getvalue().lower().startswith('no source'):
        return render_template('error.html', headermessage='No Results Found',
                               errmess='<p>'+mystdout.getvalue().replace('<', '&lt;')+'</p>')

    # Empty because of invalid input
    if len(t) == 0:
        return render_template('error.html', headermessage='Error',
                               errmess="<p>You typed: "+app_onc.vars['source_id']+"</p>")
                               
    # Add links to plot spectra and images in inventory tables
    # Direct to data_product view (/spectrum view above) with option to download
    
    # Grab object information
    objname = t['sources']['designation'][0]
    ra = t['sources']['ra'][0]
    dec = t['sources']['dec'][0]
    c = SkyCoord(ra=ra * u.degree, dec=dec * u.degree)
    coords = c.to_string('hmsdms', sep=':', precision=2)
    allnames = t['sources']['names'][0]

    # Grab distance
    try:
        distance = 1000./t['parallaxes']['parallax']
        dist_string = ', '.join(['{0:.2f}'.format(i) for i in distance])
        dist_string += ' pc'
    except:
        dist_string = 'N/A'

    # Grab spectral types; gravity indicators are ignored for now
    try:
        sptype_txt = ''
        types = np.array(t['spectral_types']['spectral_type'].tolist())
        regime = np.array(t['spectral_types']['regime'].tolist())
        if 'OPT' in regime:
            sptype_txt += 'Optical: '
            # Parse string
            ind = np.where(regime == 'OPT')
            sptype_txt += ', '.join([parse_sptype(s) for s in types[ind]])
            sptype_txt += ' '
        if 'IR' in regime:
            sptype_txt += 'Infrared: '
            ind = np.where(regime == 'IR')
            sptype_txt += ', '.join([parse_sptype(s) for s in types[ind]])
            sptype_txt += ' '
        else:
            sptype_txt += ', '.join([parse_sptype(s) for s in types])
    except:
        sptype_txt = ''

    # Grab comments
    comments = t['sources']['comments'][0]
    
    # Get external queries
    # smbd = 'http://simbad.u-strasbg.fr/simbad/sim-id?Ident='
    # vzr = 
    smbd, vzr = '', ''
    
    return render_template('inventory.html',
                           tables=[t[x].to_pandas().to_html(classes='display', index=False) for x in t.keys()],
                           titles=['na']+list(t.keys()), path=path, source_id=app_onc.vars['source_id'],
                           name=objname, coords=coords, allnames=allnames, distance=dist_string,
                           comments=comments, sptypes=sptype_txt, ra=ra, dec=dec, simbad=smbd, vizier=vzr)

    # # Photometry text
    # try:
    #     phot_data = t['photometry'].to_pandas()
    #     phot_txt = '<p>'
    #     for band in OrderedDict(sorted(phot_dict.items(), key=lambda t: t[1])):
    #         if band in phot_data['band'].tolist():
    #             unc = phot_data[phot_data['band']==band]['magnitude_unc'].values[0]
    #             if unc == 'null' or unc is None:
    #                 phot_txt += '<strong>{0}</strong>: ' \
    #                             '>{1:.2f}<br>'.format(band, phot_data[phot_data['band'] == band]['magnitude'].values[0])
    #             else:
    #                 phot_txt += '<strong>{0}</strong>: ' \
    #                             '{1:.2f} +/- {2:.2f}<br>'.format(band,
    #                                                              phot_data[phot_data['band'] == band]['magnitude'].values[0],
    #                                                              float(phot_data[phot_data['band'] == band]['magnitude_unc'].values[0]))
    #     for band in phot_data['band'].tolist():
    #         if band in phot_dict.keys():  # Skip those already displayed (which match the dictionary)
    #             continue
    #
    #         unc = phot_data[phot_data['band'] == band]['magnitude_unc'].values[0]
    #         if unc == 'null' or unc is None:
    #             phot_txt += '<strong>{0}</strong>: ' \
    #                         '>{1:.2f}<br>'.format(band, phot_data[phot_data['band'] == band]['magnitude'].values[0])
    #         else:
    #             phot_txt += '<strong>{0}</strong>: ' \
    #                         '{1:.2f} +/- {2:.2f}<br>'.format(band,
    #                                                          phot_data[phot_data['band'] == band]['magnitude'].values[0],
    #                                                          float(phot_data[phot_data['band'] == band][
    #                                                                    'magnitude_unc'].values[0]))
    #
    #     phot_txt += '</p>'
    # except:
    #     phot_txt = '<p>None in database</p>'
    #
    # # Grab spectra
    # warnings = list()
    # spectra_download = list()
    # try:
    #     spec_list = t['spectra']['id']
    #     plot_list = list()
    #
    #     for i, spec_id in enumerate(spec_list):
    #         stdout = sys.stdout  # Keep a handle on the real standard output
    #         sys.stdout = mystdout = StringIO()  # Choose a file-like object to write to
    #         query = 'SELECT spectrum, flux_units, wavelength_units, source_id, instrument_id, telescope_id ' + \
    #                 'FROM spectra WHERE id={}'.format(spec_id)
    #         q = db.query(query, fetch='one', fmt='dict')
    #         sys.stdout = stdout
    #
    #         if mystdout.getvalue().lower().startswith('could not retrieve spectrum'):
    #             warnings.append(mystdout.getvalue())
    #             continue
    #
    #         spec = q['spectrum']
    #
    #         # Get spectrum name
    #         try:
    #             query = 'SELECT name FROM telescopes WHERE id={}'.format(q['telescope_id'])
    #             n1 = db.query(query, fetch='one', fmt='array')[0]
    #             query = 'SELECT name FROM instruments WHERE id={}'.format(q['instrument_id'])
    #             n2 = db.query(query, fetch='one', fmt='array')[0]
    #             plot_name = 'Spectrum {}: {}:{}'.format(i+1, n1, n2)
    #         except:
    #             plot_name = 'Spectrum {}'.format(i+1)
    #
    #         # Make the plot
    #         tools = "resize,crosshair,pan,wheel_zoom,box_zoom,reset"
    #
    #         # create a new plot
    #         if q['wavelength_units'] is not None:
    #             wav = 'Wavelength (' + q['wavelength_units'] + ')'
    #         else:
    #             wav = 'Wavelength'
    #
    #         if q['flux_units'] is not None:
    #             flux = 'Flux (' + q['flux_units'] + ')'
    #         else:
    #             flux = 'Flux'
    #
    #         # can specify plot_width if needed
    #         p = figure(tools=tools, title=plot_name, x_axis_label=wav, y_axis_label=flux, plot_width=600)
    #
    #         p.line(spec.data[0], spec.data[1], line_width=2)
    #
    #         plot_list.append(p)
    #
    #         # Make download link
    #         query = 'SELECT spectrum FROM spectra WHERE id={}'.format(spec_id)
    #         q = db.query(query, fetch='one', fmt='dict', use_converters=False)
    #         spectra_download.append('<a href="{}" download="">Download {}</a>'.format(q['spectrum'], plot_name))
    #
    #     script, div = components(plot_list)
    # except:
    #     script, div = '', ''
    #     spectra_download = ['None in database']
        
    # return render_template('inventory.html',
    #                        tables=[t[x].to_pandas().to_html(classes='display', index=False) for x in t.keys()],
    #                        titles=['na']+list(t.keys()), path=path, source_id=app_onc.vars['source_id'],
    #                        table=phot_txt, script=script, plot=div, name=objname, coords=coords,
    #                        allnames=allnames, warnings=warnings, distance=dist_string,
    #                        comments=comments, sptypes=sptype_txt, spectra_download=spectra_download, ra=ra, dec=dec)


# Check Schema
# @app_onc.route('/schema.html', methods=['GET', 'POST'])
@app_onc.route('/schema', methods=['GET', 'POST'])
def onc_schema():
    db = astrodb.Database(db_file)
    # Get table names and their structure
    try:
        table_names = db.query("SELECT name FROM sqlite_sequence", unpack=True)[0]
    except:
        table_names = db.query("SELECT * FROM sqlite_master WHERE type='table'")['tbl_name']

    table_dict = {}
    for name in table_names:
        temptab = db.query('PRAGMA table_info('+name+')', fmt='table')
        table_dict[name] = temptab

    return render_template('schema.html',
                           tables=[table_dict[x].to_pandas().to_html(classes='display', index=False)
                                   for x in sorted(table_dict.keys())],
                           titles=['na']+sorted(table_dict.keys()))

@app_onc.route('/browse')
def onc_browse():
    """Examine the full source list with clickable links to object summaries"""
    db = astrodb.Database(db_file)
    # Run the query
    t = db.query('SELECT id, ra, dec, shortname, names, comments FROM sources', fmt='table')

    # Convert to Pandas data frame
    data = t.to_pandas()
    data.index = data['id']

    # Change column to a link
    linklist = []
    for i, elem in enumerate(zip(data['shortname'], data['names'])):
        link = '<a href="inventory/{0}">{1}<span>{2}</span></a>'.format(data.iloc[i]['id'], elem[0], elem[1])
        linklist.append(link)
    data['shortname'] = linklist
    
    # Create checkbox first column
    buttonlist = []
    for index, row in data.iterrows():
        button = '<input type="checkbox" name="{}" value="{}">'.format(str(index),repr(list(row)))
        buttonlist.append(button)
    data['Select'] = buttonlist
    cols = data.columns.tolist()
    cols.pop(cols.index('Select'))
    data = data[['Select']+cols]

    # Rename columns
    translation = {'id': 'Source ID', 'ra': '<span title="Right Ascension (deg)">RA</span>',
                   'dec': '<span title="Declination (deg)">Dec</span>', 'names': 'Alternate Designations',
                   'comments': 'Comments', 'shortname': 'Object Shortname'}
    column_names = data.columns.tolist()
    for i, name in enumerate(column_names):
        if name in translation.keys():
            column_names[i] = translation[name]
    data.columns = column_names

    # Count up photometry and spectroscopy for new columns
    df_phot = db.query('SELECT id, source_id FROM photometry', fmt='table').to_pandas()
    phot_counts = df_phot.groupby(by='source_id').count()
    phot_counts.columns = ['<span title="Amount of photometry data available">Photometry</span>']
    df_spec = db.query('SELECT id, source_id FROM spectra', fmt='table').to_pandas()
    spec_counts = df_spec.groupby(by='source_id').count()
    spec_counts.columns = ['<span title="Amount of spectroscopic observations available">Spectroscopy</span>']

    final_data = pd.concat([data, phot_counts, spec_counts], axis=1, join='outer')
    final_data['<span title="Amount of photometry data available">Photometry</span>'].fillna(value=0, inplace=True)
    final_data['<span title="Amount of spectroscopic observations available">Spectroscopy</span>'].fillna(value=0, inplace=True)

    return render_template('browse.html', table=final_data.to_html(classes='display', index=False, escape=False))


def onc_skyplot(t):
    """
    Create a sky plot of the database objects
    """
    # Convert to Pandas data frame
    data = t.to_pandas()
    data.index = data['id']

    # Remove objects without RA/Dec
    num_missing = np.sum(pd.isnull(data['ra']))
    if num_missing > 0:
        warning_message = 'Note: {} objects had missing coordinate information and were removed.'.format(num_missing)
        data = data[pd.notnull(data['ra'])]
    else:
        warning_message = ''

    # Coerce to numeric
    data['ra'] = pd.to_numeric(data['ra'])
    data['dec'] = pd.to_numeric(data['dec'])

    # Coordinate conversion
    c = SkyCoord(ra=data['ra'] * u.degree, dec=data['dec'] * u.degree)
    pi = np.pi
    proj = 'hammer'
    data['x'], data['y'] = projection(c.ra.radian - pi, c.dec.radian, use=proj)
    data['l'], data['b'] = c.galactic.l, c.galactic.b

    # Make the plots
    p1 = make_sky_plot(data, proj)
    data['x'], data['y'] = projection(c.galactic.l.radian - pi, c.galactic.b.radian, use=proj)
    p2 = make_sky_plot(data, proj)

    tab1 = Panel(child=p1, title="Equatorial")
    tab2 = Panel(child=p2, title="Galactic")
    tabs = Tabs(tabs=[tab1, tab2])

    script, div = components(tabs)

    return script, div, warning_message


@app_onc.route('/feedback')
def onc_feedback():
    return render_template('feedback.html')

def projection(lon, lat, use='hammer'):
    """
    Convert x,y to Aitoff or Hammer projection. Lat and Lon should be in radians. RA=lon, Dec=lat
    """
    # TODO: Figure out why Aitoff is failing

    # Note that np.sinc is normalized (hence the division by pi)
    if use.lower() == 'hammer': # Hammer
        x = 2.0 ** 1.5 * np.cos(lat) * np.sin(lon / 2.0) / np.sqrt(1.0 + np.cos(lat) * np.cos(lon / 2.0))
        y = sqrt(2.0) * np.sin(lat) / np.sqrt(1.0 + np.cos(lat) * np.cos(lon / 2.0))
    else:  # Aitoff, not yet working
        alpha_c = np.arccos(np.cos(lat) * np.cos(lon / 2.0))
        x = 2.0 * np.cos(lat) * np.sin(lon) / np.sinc(alpha_c / np.pi)
        y = np.sin(lat) / np.sinc(alpha_c / np.pi)
    return x, y


def make_sky_plot(data, proj='hammer'):
    """
    Make a sky plot and return a Bokeh figure
    Adapted from: https://github.com/astrocatalogs/astrocats/blob/master/scripts/hammertime.py#L93-L132 and the Open Supernova Catalog (https://sne.space/statistics/sky-locations/)
    """
    source = ColumnDataSource(data=data)

    tools = "resize,tap,pan,wheel_zoom,box_zoom,reset"
    p = figure(tools=tools, title='', plot_width=800, plot_height=600,
               x_range=(-1.05 * (2.0 ** 1.5), 1.3 * 2.0 ** 1.5), y_range=(-2.0 * sqrt(2.0), 1.2 * sqrt(2.0)),
               min_border=0, min_border_bottom=0)

    # Initial figure formatting
    p.axis.visible = None
    p.outline_line_color = None
    p.xgrid.grid_line_color = None
    p.ygrid.grid_line_color = None

    # Add the grid
    pi = np.pi
    rangepts = 50
    raseps = 12
    decseps = 12
    rarange = [-pi + i * 2.0 * pi / rangepts for i in range(0, rangepts + 1)]
    decrange = [-pi / 2.0 + i * pi / rangepts for i in range(0, rangepts + 1)]
    ragrid = [-pi + i * 2.0 * pi / raseps for i in range(0, raseps + 1)]
    decgrid = [-pi / 2.0 + i * pi / decseps for i in range(0, decseps + 1)]

    raxs = []
    rays = []
    for rg in ragrid:
        t1 = [projection(rg, x, use=proj) for x in decrange]
        tx, ty = zip(*t1)
        raxs.append(tx)
        rays.append(ty)

    decxs = []
    decys = []
    for dg in decgrid:
        t1 = [projection(x, dg, use=proj) for x in rarange]
        tx, ty = zip(*t1)
        decxs.append(tx)
        decys.append(ty)

    p.multi_line(raxs, rays, color='#bbbbbb')
    p.multi_line(decxs, decys, color='#bbbbbb')

    # Add the data
    p.scatter('x', 'y', source=source, size=8, alpha=0.6)
    tooltip = [("Source ID", "@id"), ("Name", "@shortname"), ("(RA, Dec)", "(@ra, @dec)"), ("(l, b)", "(@l, @b)")]
    p.add_tools(HoverTool(tooltips=tooltip))

    # When clicked, go to the Summary page
    url = "summary/@id"
    taptool = p.select(type=TapTool)
    taptool.callback = OpenURL(url=url)

    return p


# Photometry dictionary in microns
phot_dict = {'J': 1.24, 'H': 1.66, 'K': 2.19, 'Ks': 2.16, 'W1': 3.35, 'W2': 4.6, 'W3': 11.56, 'W4': 22.09,
             '[3.6]': 3.51, '[4.5]': 4.44, '[5.8]': 5.63, '[8]': 7.59, '[24]': 23.68, 'g': .48, 'i': .76, 'r': .62,
             'u': .35, 'z': .91, '2MASS_J': 1.24, '2MASS_H': 1.66, '2MASS_Ks': 2.16, 'WISE_W1': 3.35,
             'WISE_W2': 4.6, 'WISE_W3': 11.56, 'WISE_W4': 22.09, 'IRAC_ch1': 3.51, 'IRAC_ch2': 4.44,
             'IRAC_ch3': 5.63, 'IRAC_ch4': 7.59, 'SDSS_g': .48, 'SDSS_i': .76, 'SDSS_r': .62, 'SDSS_u': .35,
             'SDSS_z': .91, 'HST_F105W': 1.0552, 'HST_F110W': 1.1534, 'HST_F125W': 1.2486, 'HST_F140W': 1.3923,
             'Johnson_B': 0.442, 'Johnson_U': 0.364, 'Johnson_V': 0.540,
             'MKO_H': 1.635, 'MKO_J': 1.25, 'MKO_K': 2.20, "MKO_L'": 3.77, "MKO_M'": 4.68, 'MKO_Y': 1.02,
             'DENIS_I': 0.82, 'DENIS_J': 1.25, 'DENIS_K': 2.15, 'DENIS_Ks': 2.15,
             'Cousins_I': 0.647, 'Cousins_R': 0.7865,
             'I': 0.806, 'L': 3.45, 'Y': 1.02, 'Z': 0.9, 'y': 1.02,
             'GALEX_FUV': 0.1528, 'GALEX_NUV': 0.2271,
             'FourStar_J2': 1.144, 'FourStar_J3': 1.287}

def parse_sptype(spnum):
    """Parse a spectral type number and return a string"""

    # Attempt to convert to float
    try:
        spnum = float(spnum)
    except ValueError:
        pass

    if spnum >= 30:
        sptxt = 'Y'
    if (spnum >= 20) & (spnum < 30):
        sptxt = 'T'
    if (spnum >= 10) & (spnum < 20):
        sptxt = 'L'
    if (spnum >= 0) & (spnum < 10):
        sptxt = 'M'
    if spnum < 0:
        sptxt = 'K'

    if isinstance(spnum, type('')):
        sptxt = spnum
    else:
        sptxt += '{0:.1f}'.format(abs(spnum) % 10)

    return sptxt
    
    
    
    
    
    