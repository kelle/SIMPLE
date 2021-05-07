# Tests to verify database contents

import os
import pytest
from simple.schema import *
from astrodbkit2.astrodb import create_database, Database
from sqlalchemy import *

DB_NAME = 'temp.db'
DB_PATH = 'data'


# Load the database for use in individual tests
@pytest.fixture(scope="module")
def db():
    # Create a fresh temporary database and assert it exists
    # Because we've imported simple.schema, we will be using that schema for the database

    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)
    connection_string = 'sqlite:///' + DB_NAME
    create_database(connection_string)
    assert os.path.exists(DB_NAME)

    # Connect to the new database and confirm it has the Sources table
    db = Database(connection_string)
    assert db
    assert 'source' in [c.name for c in db.Sources.columns]

    # Load the database contents
    # This should take care of finding serious issues (key/column violations)
    db.load_database(DB_PATH, verbose=False)

    return db


# Utility functions
# -----------------------------------------------------------------------------------------
def reference_verifier(t, name, bibcode, doi):
    # Utility function to verify reference values in a table
    ind = t['name'] == name
    assert t[ind]['bibcode'][0] == bibcode, f'{name} did not match bibcode'
    assert t[ind]['doi'][0] == doi, f'{name} did not match doi'


# Individual ingest tests
# -----------------------------------------------------------------------------------------
def test_Manj19_data(db):
    """
    Tests for data ingested from Manjavacas+2019

    Data file(s):
        ATLAS_table.vot

    Ingest script(s):
        ingest_ATLAS_sources.py
        ingest_ATLAS_spectral_types.py
    """

    pub = 'Manj19'

    # Test total spectral types added
    n_Manj19_types = db.query(db.SpectralTypes).filter(db.SpectralTypes.c.reference == pub).count()
    assert n_Manj19_types == 40, f'found {n_Manj19_types} sources for {pub}'

    # Test number of L types added
    n_Manj19_Ltypes = db.query(db.SpectralTypes).filter(and_(db.SpectralTypes.c.spectral_type_code >= 70,
                                                             db.SpectralTypes.c.spectral_type_code < 80,
                                                             db.SpectralTypes.c.reference == pub)).count()
    assert n_Manj19_Ltypes == 19, f'found {n_Manj19_Ltypes} L type dwarfs for {pub}'

    # Test number of T types added
    n_Manj19_Ttypes = db.query(db.SpectralTypes).filter(and_(db.SpectralTypes.c.spectral_type_code >= 80,
                                                             db.SpectralTypes.c.spectral_type_code < 90,
                                                             db.SpectralTypes.c.reference == pub)).count()
    assert n_Manj19_Ttypes == 21, f'found {n_Manj19_Ttypes} T type dwarfs for {pub}'

def test_Manj19_pub(db):
    pub = 'Manj19'

    # Check DOI and Bibcode values are correctly set for new publications added
    manj19_pub = db.query(db.Publications).filter(db.Publications.c.name == pub).astropy()
    reference_verifier(manj19_pub, 'Manj19', '2019AJ....157..101M', '10.3847/1538-3881/aaf88f')


def test_Kirk19_ingest(db):
    """
    Tests for Y-dwarf data ingested from Kirkpartick+2019

    Data file(s):
        Y-dwarf_table.csv

    Ingest script(s):
        Y_dwarf_source_ingest.py
        Y-dwarf_SpT_ingest.py
        Y-dwarf_astrometry-ingest.py

    """

    # Reference tests
    # -----------------------------------------------------------------------------------------

    # Test refereces added
    ref_list = ['Tinn18', 'Pinf14', 'Mace13', 'Kirk12', 'Cush11', 'Kirk13',
                'Schn15', 'Luhm14b', 'Tinn14', 'Tinn12', 'Cush14', 'Kirk19']
    t = db.query(db.Publications).filter(db.Publications.c.name.in_(ref_list)).astropy()

    if len(ref_list) != len(t):
        missing_ref = list(set(ref_list)-set(t['name']))
        assert len(ref_list) == len(t), f'Missing references: {missing_ref}'

    # Check DOI and Bibcode values are correctly set for new references added
    reference_verifier(t, 'Kirk19', '2019ApJS..240...19K', '10.3847/1538-4365/aaf6af')
    reference_verifier(t, 'Pinf14', '2014MNRAS.444.1931P', '10.1093/mnras/stu1540')
    reference_verifier(t, 'Tinn18', '2018ApJS..236...28T', '10.3847/1538-4365/aabad3')

    # Data tests
    # -----------------------------------------------------------------------------------------

    # Test sources added
    ref = 'Pinf14'
    t = db.query(db.Sources).filter(db.Sources.c.reference == ref).astropy()
    assert len(t) == 1, f'found {len(t)} sources for {ref}'

    # Test spectral types added

    # Test parallaxes added
    ref = 'Kirk19'
    t = db.query(db.Parallaxes).filter(db.Parallaxes.c.reference == ref).astropy()
    assert len(t) == 22, f'found {len(t)} parallax entries for {ref}'
