#!/usr/bin/env python3
"""Pull symbols out of KiCad's installed standard libraries.

The EC9 project had to invent every symbol and footprint because KiCad was not
installed when it was generated, which is why everything there carries an
UNVALIDATED stamp. Here the full standard library is present, so symbols are
taken from it and embedded into each sheet's `lib_symbols` block with the lib_id
still pointing at the real library (e.g. `Isolator:6N137`). Geometry and pin
numbering are therefore the community-maintained ones.

Two wrinkles in the library format that this handles:

* **`extends`** - most variants are derived symbols carrying only their own
  properties, with the graphics and pins living in a base symbol (`6N137`
  extends `HCPL-261A`, `74HC123` extends `74LS123`). A schematic embeds the
  fully resolved symbol, so the base's sub-symbols are merged in and renamed.
* **empty pin names** - many symbols use `(name "")`, so the pin-name pattern
  must accept an empty string or those pins vanish silently.
"""
import os
import re

SYM_DIR = os.environ.get('KICAD_SYMBOL_DIR', 'D:/KiCad/share/kicad/symbols')

_CACHE = {}


def _span(s, start):
    """End index of the balanced s-expression at or after `start`."""
    depth = 0
    for j in range(start, len(s)):
        if s[j] == '(':
            depth += 1
        elif s[j] == ')':
            depth -= 1
            if depth == 0:
                return j + 1
    raise ValueError('unbalanced s-expression')


def _lib_text(lib):
    if lib not in _CACHE:
        path = os.path.join(SYM_DIR, lib + '.kicad_sym').replace('\\', '/')
        with open(path, encoding='utf-8') as f:
            _CACHE[lib] = f.read()
    return _CACHE[lib]


def raw_symbol(lib, name):
    """The verbatim top-level `(symbol "name" ...)` block."""
    s = _lib_text(lib)
    i = s.find('\n\t(symbol "%s"' % name)
    if i < 0:
        raise KeyError('%s not found in %s' % (name, lib))
    start = s.index('(', i)
    return s[start:_span(s, start)]


def base_of(lib, name):
    """Name this symbol extends, or None."""
    m = re.search(r'\(extends "([^"]+)"', raw_symbol(lib, name))
    return m.group(1) if m else None


def _subsymbols(lib, name):
    """Verbatim sub-symbol blocks (`name_0_1`, `name_1_1`, ...)."""
    s = _lib_text(lib)
    out = []
    for m in re.finditer(r'\n\t\t\(symbol "(%s_\d+_\d+)"' % re.escape(name), s):
        start = s.index('(', m.start())
        out.append((m.group(1), s[start:_span(s, start)]))
    return out



def _toplevel_items(block):
    """[(key, text)] for each top-level child of a symbol block.

    `key` is ('property', <name>) for properties so they can be matched by name,
    and (<head>,) otherwise.
    """
    out = []
    for m in re.finditer(r'\n\t\t\(([a-z_]+)', block):
        start = block.index('(', m.start())
        text = block[start:_span(block, start)]
        head = m.group(1)
        if head == 'property':
            nm = re.match(r'\(property "([^"]*)"', text)
            out.append((('property', nm.group(1) if nm else ''), text))
        else:
            out.append(((head,), text))
    return out


def _toplevel_keys(block):
    return {k for k, _ in _toplevel_items(block)}


def resolve(lib, name):
    """Fully resolved symbol body: own properties plus the base's graphics.

    Returns the inner text of the `(symbol ...)` block, without its own header
    and closing paren, so callers can wrap it under whatever lib_id they want.
    """
    blk = raw_symbol(lib, name)
    inner = blk[blk.index('"%s"' % name) + len(name) + 2:-1]
    base = base_of(lib, name)
    if base is None:
        return inner
    # Drop the (extends ...) marker, keep this symbol's own properties.
    i = inner.find('(extends ')
    inner = inner[:i] + inner[_span(inner, i):]
    # Inherit every top-level attribute the derived symbol does not define for
    # itself. A derived symbol usually carries only Reference/Value/Footprint/
    # Datasheet/Description and the ki_* hints, leaving pin_names, in_bom,
    # on_board, exclude_from_sim, in_pos_files, duplicate_pin_numbers_are_jumpers
    # and ki_locked to the base. Missing any of them makes the embedded copy
    # differ from the library and KiCad reports lib_symbol_mismatch.
    bblk = raw_symbol(lib, base)
    have = _toplevel_keys(inner)
    add = []
    for key, text in _toplevel_items(bblk):
        if key[0] == 'symbol':          # graphics are merged separately below
            continue
        if key not in have:
            add.append(text)
    inner = ''.join('\n\t\t' + t for t in add) + inner
    # Merge in graphics, renamed to this symbol. The chain can be more than one
    # link deep - JQC-3FF-024-1Z extends JQC-3FF-005-1Z extends Relay_SPDT - and
    # only the last link actually carries sub-symbols.
    src, subs = base, _subsymbols(lib, base)
    while not subs:
        nxt = base_of(lib, src)
        if nxt is None:
            break
        src, subs = nxt, _subsymbols(lib, nxt)
    for sub_name, sub in subs:
        inner += sub.replace('"%s"' % sub_name,
                             '"%s"' % sub_name.replace(src, name, 1), 1)
    return inner


def embedded(lib, name):
    """Fully resolved symbol, named `lib:name`, ready for a sheet lib_symbols."""
    return '(symbol "%s:%s"%s)' % (lib, name, resolve(lib, name))


_PIN = re.compile(r'\(pin (\w+) (\w+)')


def units(lib, name):
    """Unit numbers a symbol defines. Multi-unit parts split gates across them,
    usually with the highest unit holding only the power pins."""
    body = resolve(lib, name)
    return sorted({int(m.group(1))
                   for m in re.finditer(r'\(symbol "[^"]+_(\d+)_\d+"', body)})


def pins(lib, name, unit=None):
    """[{num, name, type, x, y, angle, unit}] for a symbol, resolving `extends`.

    With `unit` given, returns only that unit's pins plus any in unit 0, which
    is the sub-symbol shared by every unit. Deduplicates by pin number: a part
    may draw the same pin in more than one body style (De Morgan alternative).
    """
    body = resolve(lib, name)
    out, seen = [], set()
    for sm in re.finditer(r'\(symbol "[^"]+_(\d+)_\d+"', body):
        u = int(sm.group(1))
        if unit is not None and u not in (0, unit):
            continue
        blk = body[sm.start():_span(body, sm.start())]
        for pm in _PIN.finditer(blk):
            pblk = blk[pm.start():_span(blk, pm.start())]
            num = re.search(r'\(number "([^"]*)"', pblk)
            nm = re.search(r'\(name "([^"]*)"', pblk)
            at = re.search(r'\(at (-?[\d.]+) (-?[\d.]+)(?: (-?[\d.]+))?', pblk)
            if not (num and at) or num.group(1) in seen:
                continue
            seen.add(num.group(1))
            out.append({'num': num.group(1),
                        'name': nm.group(1) if nm else '',
                        'type': pm.group(1),
                        'x': float(at.group(1)), 'y': float(at.group(2)),
                        'angle': float(at.group(3) or 0), 'unit': u})
    if unit is None and not out:
        # Single-unit symbols keep their pins directly in the body.
        for pm in _PIN.finditer(body):
            pblk = body[pm.start():_span(body, pm.start())]
            num = re.search(r'\(number "([^"]*)"', pblk)
            nm = re.search(r'\(name "([^"]*)"', pblk)
            at = re.search(r'\(at (-?[\d.]+) (-?[\d.]+)(?: (-?[\d.]+))?', pblk)
            if num and at and num.group(1) not in seen:
                seen.add(num.group(1))
                out.append({'num': num.group(1),
                            'name': nm.group(1) if nm else '',
                            'type': pm.group(1),
                            'x': float(at.group(1)), 'y': float(at.group(2)),
                            'angle': float(at.group(3) or 0), 'unit': 1})
    return out


def prop(lib, name, field):
    m = re.search(r'\(property "%s" "([^"]*)"' % re.escape(field),
                  raw_symbol(lib, name))
    return m.group(1) if m else None


if __name__ == '__main__':
    import sys
    lib, name = sys.argv[1], sys.argv[2]
    print('%s:%s   extends=%s   footprint=%s'
          % (lib, name, base_of(lib, name), prop(lib, name, 'Footprint')))
    for p in pins(lib, name):
        print('   %-4s %-14s %-14s (%g, %g) %g'
              % (p['num'], p['name'] or '-', p['type'], p['x'], p['y'], p['angle']))
