# spice-waveform-gen
Set of scripts that make use of a compact notation for specifying inputs and
expected outputs of SPICE simulation.
* `bus2pwl.py` is used to generate a SPICE PWL file that can be `.import`ed
into a SPICE netlist to specify inputs for a device under test.
* `busverify.py` reads a rawfile output by LTSPICE (and possibly other SPICE
variants) and verifies that the waveform reflects the outputs specified in
the bus file.

## Bus Files
### Syntax Specification
`busparse.py` is responsible for parsing the information from a bus file
into a more useful form for `bus2pwl.py` or `busverify.py`. There are
several example bus files in the 'examples' directory that one could
examine if they were having trouble writing a bus file. There's also a
file in the examples directory called 'template.bus' that contains
instructions to help you create your first bus file.
#### General Rules:
* For now, bus parsing is case sensitive (It shouldn't be - SPICE isn't,
why would a bus file be? I'll fix this soon).
* Whitespace is not important
* Comment lines start with '#'
* Numbers accept post-fixes (e.g. 1n for 1 nanosecond)
### Sections:
#### Parameters
The first non-comment lines of a bus file are assumed to contain information
about the clock, logic 'hi' and 'lo' voltages, and transition times that
should be used when the PWL is written. The options that can currently be
specified here are:
* `risefall` (required) - rise and fall times for your inputs
* `bittime` (required) - The number of time that a bit will be low and high.
The period of your clock will be twice this number.
* `bitlow` (required) - The voltage of a logic 'lo' signal
* `bithigh` (required) - The voltage of a logic 'hi' signal
* `clockdelay` - The time by which the clock signal transitions will
lag input signal transitions.
* `clockrisefall` - Allows specification of a different transition time for
the clock signal.

These parameters are assigned in any order, one per line, on the first non-comment lines
of the bus file using the form: `clockrisefall = 100p` (or similar). Again,
whitepace is not important - `clockrisefall=100p` is just as good.
#### Signals
The beginning of the signals block is denoted by putting: `Signals:` on its own line.
The next line contains alphanumeric signal names. These are not checked for compatibility
with SPICE - the line is simply tokenized and the tokens get stored as signals.

You can, however, specify a bus here using the notation: `name[x:y]` where name is the
name of the signal and x and y represent the bitslice from a bus that the signal represents. 
x and y can be specified in either order (think VHDL `downto` vs `to`), but the order in
which vectors are specified must match the order in which bus signals are specified.
Internally, this 'bus' notation is simply expanded into a bunch of individual signals
with names `name[x], name[x-1]... name[y]`, so these signals will be interpretted correctly
by SPICE. 

#### Vectors:
The `Vectors:` section, which is expected to follow the `Signals:` section,
allows you to specify the logic 1s and 0s that will get written to
the PWL as voltages. You can specify these voltages using any of several notations, and, as before,
whitespace does not matter. That means that if your signals are: `data[7:0] addr[7:0]`, you can specify
your vectors using any of the following forms:  
`0000000000000000`
`00000000 00000000`
`00 00 0000 00000 000`  
There is no 'grouping' of values.

If there is no prefix on number in the 'vectors' section of the busfile, it is assumed
to be a binary literal. If a number in the vectors section of the file starts with '0b',
it is definitely a binary literal. If a number starts with '0x' it is interpreted as hex.
There is a caveat to hex notation though - every hex digit specifies exactly four bits.
0x0 gets expanded to 0000, 0x00 gets expanded to 00000000, etc. 0, by itself, does not
get expanded. 0 != 0x0 != 0x00.

The real power of the bus file lies in the ability to specify ranges of vectors. This is
done using the syntax: `[nbits](val1,val2)`. nbits is the number of bits that the range
will stake up. Val1 and Val2 specify the beginning (inclusive) and end (exclusive) of
the range of values that the expanded range will span. If val1 is larger than val2, the
range will 'count down' from val1 to val2, and if val1 is smaller than val2, the range
will 'count up' from val1 to val2.

One thing to keep in mind when you're specifying ranges - one cannot specify two ranges
with different spans on the same line. For example, you could not write:
`[8](0,15) [8](0,4)`: one of the ranges is attempting to represent the values 0-15, and
the other is trying to represent 0-4. You can, however, specify the following:
`[8](0,15) 0x00`. In this case, the first 8 bits will increase from 0-15 while the 
second 8 bits are always 0.

#### Output
Though the verification script is not yet functional, the parser can handle an `Outputs:`
section. It works the same way as the signals section.

#### Vectors (for outputs)
A second `Vectors:` section must follow an `Outputs:` section. It works exactly the same
as the vectors section for the signals.
