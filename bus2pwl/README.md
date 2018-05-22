# bus2pwl
Script used to convert a `.bus` file, which compactly specifies how a series of waveforms changes with time, to a series of piecewise linear voltage sources that can be `.import`ed  to a spice file and used to simualte a subcircuit.

## Usage
`python bus2pwl.py [-v] inputfile.bus`

## Bus file format specification
Eventually, there will be a detailed sytax specification here. For now, take a look at the cryptic guidelines in brackets and the example file, which is useful for simulating a full adder.

### Cryptic Guidelines
[one name=value parameter per line]
[space-separated column labels for voltage source names AND node names]
[one line per bit interval of 0 or 1 for each column, no spaces between]

The "clockdelay=" parameter, if present, also generates a voltage source for a
clock as "Vclock clock 0 PWL ..." with a rising edge at every bittime with an
offset of clockdelay.  Hence, set "clockdelay=" to the maximum setup time of
your registers and the data on each line will be clocked in at the right time.
Parameter "clockrisefall=" is optional to separately specify the clock rise/
fall time if it is different from the data lines rise/fall.

### Example .bus contents for testing an adder
```
clockdelay=500p
clockrisefall = 100p
risefall=200p
bittime=1n
bitlow=0
bithigh=5
a3 a2 a1 a0 b3 b2 b1 b0
00000000
00010001
00010010
11111111
01011010
01011011
```

Include the generated file, which also includes the Voltage-source definitons
for the input nodes as: `.include "foo.pwl"`


