# k2000

[![Python package](https://github.com/psobot/k2000/actions/workflows/test.yaml/badge.svg)](https://github.com/psobot/k2000/actions/workflows/test.yaml)

A Python package for communicating with the Kurzweil K2000/K2500/K2600 family of synthesizers over MIDI.

![Screenshot](https://user-images.githubusercontent.com/213293/209573494-75bc8f4d-0696-4758-a6bb-b4d619a549f9.PNG)

```
pip install k2000
```

### _What?_

Back in the 1990s, [Kurzweil Music Systems](https://en.wikipedia.org/wiki/Kurzweil_Music_Systems) - founded by Raymond Kurzweil and Stevie Wonder - released an extremely advanced line of synthesizers known as [the _K2_ series](https://en.wikipedia.org/wiki/Kurzweil_Music_Systems#K2xxx_synthesizers). Compared to the music technology we have today in the mid-2020s, these synthesizers were... actually not bad. They still hold up today.

This library contains code for communicating with an attached K2-series synthesizer (specifically the **K2000, K2500, or K2600**) via MIDI, implementing its entire SysEx protocol, allowing for full interface control and full object read and write support.

### _How?_

A quick-start example:
```python
from k2000.client import K2500Client

c = K2500Client("My MIDI Interface Name")
assert c.is_connected

print(c.get_screen_text())
# ProgramMode    Xpose:0ST   <>Channel:1  
#                     998 Choral Sleigh   
# KeyMap Info         999 Pad Nine        
#  Grand Piano          1 Acoustic Piano  
#  Syn Piano            2 Stage Piano     
#                       3 BriteGrand      
#                       4 ClassicPiano&Vox
# Octav- Octav+ Panic  Sample Chan-  Chan+

# Navigate around the UI a bit:
c.up()
c.down()
c.number(125)
c.enter()

# Access object data:
name, program_data = c.programs[125]
print(f"Got {len(program_data):,} bytes of program data for Program \"{name}\".")
# prints: Got 586 bytes of program data for Program "Fast Solo Tenor".

# Dump all effect data, for example:
for i, value in c.effects.items():
    if value is None:
        continue
    effect_name, effect_data = value
    do_something_with(effect_name, effect_data)

# Take screenshots!
image = c.screenshot()
image.save("screenshot.png")
# Which gives...
```

![K2000 Screenshot](https://user-images.githubusercontent.com/213293/209573340-bb42ebea-7d09-492a-baec-c993a31a6051.PNG)

### _Why?_

I was doing some reverse engineering and this library helped make that reverse engineering easier.

More generally, though; you could use this library if you wanted to:
 - Load or dump programs (or setups, or effects, etc) from your K2-series synth via Python.
 - Control the interface of your K2-series synth (i.e. push buttons, read the text and graphics) over MIDI
 - Take screenshots of your K2's display over MIDI
 - Automate the control of your K2 for scraping, testing, etc.

Ironically, this library doesn't support sending MIDI notes; just the SysEx commands to control specific functions of the K2.

### License

```
MIT License

Copyright (c) 2019-2023 Peter Sobot

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```