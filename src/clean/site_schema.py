"""Master site table contract. Identifiers must remain strings on CSV reload."""

MASTER_SITE_SCHEMA = {
    'site_id': 'string',
    'source': 'string',
    'source_version': 'string',
    'source_site_id': 'string',
    'site_name': 'string',
    'state': 'string',
    'state_abbr': 'string',
    'state_fips': 'string',
    'county': 'string',
    'county_fips': 'string',
    'longitude': 'Float64',
    'latitude': 'Float64',
    # IM3 README.pdf p. 2: facility polygon surface area; not usable floor area.
    'square_feet': 'Float64',
    'operator': 'string',
    'operator_raw': 'string',
    'site_type': 'string',
    'reference': 'string',
    'quality_flags': 'string',
}
SITE_TYPES = {'building', 'campus', 'point'}
