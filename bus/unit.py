from decimal import Decimal
import logging
import re

Unit_regexp = re.compile(r'^([0-9e\+\-\.]+)(t|g|meg|x|k|mil|m|u|n|p|f)?')
'''Returns a Decimal equivalent to a string with number and SPICE unit'''

def unit(s):
    """Takes a string and returns the equivalent float.
    '3.0u' -> 3.0e-6"""
    mult = {'t'  :Decimal('1.0e12'),
            'g'  :Decimal('1.0e9'),
            'meg':Decimal('1.0e6'),
            'x'  :Decimal('1.0e6'),
            'k'  :Decimal('1.0e3'),
            'mil':Decimal('25.4e-6'),
            'm'  :Decimal('1.0e-3'),
            'u'  :Decimal('1.0e-6'),
            'n'  :Decimal('1.0e-9'),
            'p'  :Decimal('1.0e-12'),
            'f'  :Decimal('1.0e-15')}

    m = Unit_regexp.search(s.lower())

    try:
        if m.group(2):
            return Decimal(Decimal(m.group(1)))*mult[m.group(2)]
        else:
            return Decimal(m.group(1))
    except:
        logging.error("Bad unit: %s" % s)
