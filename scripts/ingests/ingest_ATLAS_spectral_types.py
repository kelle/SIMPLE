# ------------------------------------------------------------------------------------------------

from astrodbkit2.astrodb import create_database
from astrodbkit2.astrodb import Database
from simple.schema import *
from astropy.table import Table
import numpy as np
import re
import os
from utils import convert_spt_string_to_code

DRY_RUN = True
RECREATE_DB = True
VERBOSE = False

verboseprint = print if VERBOSE else lambda *a, **k: None

db_file = 'SIMPLE.db'
db_connection_string = 'sqlite:///SIMPLE.db'  # SQLite

try:
	db_file_path = db_file.resolve(strict=True)
except:
	# SIMPLE.db file does not exist so create it
	create_database(db_connection_string)
	db = Database(db_connection_string)
	db.load_database('data')
else:
	# SIMPLE.db file does exist
	if RECREATE_DB: # Recreate database anyway
		os.remove(db_file)
		create_database(db_connection_string)
		db = Database(db_connection_string)
		db.load_database('data')
	else: # Use pre-existing database
		db = Database(db_connection_string)

# ===============================================================
# Ingest new reference if missing
# ===============================================================

# Adding new reference Manj19 to publications table in database
manj19_search = db.query(db.Publications).filter(db.Publications.c.name == 'Manj19').table()
if len(manj19_search) == 0 and not DRY_RUN:
	new_ref = [{'name': 'Manj19'}]
	# Should have included bibcode and doi
	# new_ref = [{'name': 'Manj19', 'bibcode': '2019AJ....157..101M', 'doi': '10.3847/1538-3881/aaf88f'}]
	db.Publications.insert().execute(new_ref)

#add DOI and Bibcode after Manj19 already added
add_doi_bibcode = db.Publications.update().where(db.Publications.c.name == 'Manj19').\
	values(bibcode='2019AJ....157..101M', doi='10.3847/1538-3881/aaf88f', description='Cloud Atlas: HST nir spectral library')
db.engine.execute(add_doi_bibcode)
# ===============================================================


# load table of sources to ingest
ingest_table = Table.read("scripts/ingests/ATLAS_table.vot")
ingest_table_df = ingest_table.to_pandas()
names = ingest_table['Name']
n_sources = len(names)
spectral_types_unknown = ingest_table['SpType']  # pre-existing spectral types
spectral_types_spex = ingest_table['SpTSpeX']  # new spectral types

# fetch primary name identifier from database
db_names = []
for name in names:
	db_name = db.search_object(name, output_table='Sources')[0].source
	db_names.append(db_name)

# ===============================================================
#   Ingest new spectral type estimates
#   from the SpTSpeX column
# ===============================================================

db_names_spex = []
spex_types_string = []
for i, db_name in enumerate(db_names):
	if spectral_types_spex[i] != "":
		db_names_spex.append(db_name)
		spex_types_string.append(spectral_types_spex[i])

spex_types_codes = convert_spt_string_to_code(spex_types_string, verbose=False)
regime = ['nir'] * len(db_names_spex)
spt_ref = ['Manj19'] * len(db_names_spex)
# adopted = False * len(db_names_spex) # Should have specified adopted column
SpT_table_spex = Table([db_names_spex, spex_types_string, spex_types_codes, regime, spt_ref],
					   names=('source', 'spectral_type_string', 'spectral_type_code', 'regime', 'reference'))
SpT_table_spex_df = SpT_table_spex.to_pandas()  # make a Pandas dataframe to explore  with Pycharm

# Report results
print("\n",len(db_names_spex),"Spex SpTypes to be added")
verboseprint(SpT_table_spex_df)

# Add to database
if not DRY_RUN:
	db.add_table_data(SpT_table_spex, table='SpectralTypes', fmt='astropy')

# Update adopted field after spectral types were already added
update_adopted = db.SpectralTypes.update().where(db.SpectralTypes.c.reference == 'Manj19').values(adopted=False)
db.engine.execute(update_adopted)

# Verify results
n_Manj19_types = db.query(db.SpectralTypes).filter(db.SpectralTypes.c.reference == 'Manj19').count()
print("\n",n_Manj19_types, 'spectral types referenced to Manj19 now found database')
verboseprint(db.query(db.SpectralTypes).filter(db.SpectralTypes.c.reference == 'Manj19').table())

# Deletion example (use with caution!)
# db.SpectralTypes.delete().where(db.SpectralTypes.c.reference == 'Manj19').execute()
# ===============================================================


# ===============================================================
#     Ingest spectral types from unknown sources
#     if sources have no other spectral type
# ===============================================================

# Find out which sources don't have spectral types
db_names_needs_spectral_type = []
spectral_types_to_add = []
for i, db_name in enumerate(db_names):
	db_spectral_types = db.query(db.SpectralTypes).filter(db.SpectralTypes.c.source == db_name).table()
	if db_spectral_types is None or len(db_spectral_types) == 0:
		db_names_needs_spectral_type.append(db_name)
		spectral_types_to_add.append(spectral_types_unknown[i])

# Convert SpT string to code
spectral_type_codes_unknown = convert_spt_string_to_code(spectral_types_to_add, verbose=False)
regime = ['unknown'] * len(db_names_needs_spectral_type)
spt_ref = ['Missing'] * len(db_names_needs_spectral_type)
comments = ['From ATLAS Table Manjavacas etal. 2019']*len(db_names_needs_spectral_type)
# adopted = False * len(db_names_needs_spectral_type) # Should have specified adopted column
SpT_table_unknown = Table([db_names_needs_spectral_type, spectral_types_to_add, spectral_type_codes_unknown, regime,
						   spt_ref, comments],
						names=('source', 'spectral_type_string', 'spectral_type_code', 'regime', 'reference',
							   'comments'))

# Report the results
print("\n",len(db_names_needs_spectral_type),"Spectral types with Missing reference to be added")

# Add to database
if not DRY_RUN:
	db.add_table_data(SpT_table_unknown, table='SpectralTypes', fmt='astropy')

update_adopted = db.SpectralTypes.update().where(db.SpectralTypes.c.reference == 'Missing').values(adopted=False)
db.engine.execute(update_adopted)

# Deletion example. Undos add_table_data. (use with caution!)
# db.SpectralTypes.delete().where(db.SpectralTypes.c.reference == 'Missing').execute()
# ===============================================================

#if not DRY_RUN:
db.save_db('data')
