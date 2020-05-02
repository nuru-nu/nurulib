import collections


# parse palettes
###############################################################################

ColorPoint = collections.namedtuple('ColorPoint', ['index', 'color'])


def parse_colors_co_scss(scss):
    """Copy'n'paste color.co's SCSS palettes."""
    rgbs = [
        [float(v) / 256
         for v in line[line.index('(') + 1:line.index(')')].split(', ')[:3]]
        for line in scss.split('\n')
        if line
    ]
    return [
        ColorPoint(i / len(rgbs), rgb)
        for i, rgb in enumerate(rgbs)
    ]


def hex_to_tuple(s):
    """Converts #FFFFFF (or #FFF) to (1, 1, 1)."""
    if s[0] == '#':
        s = s[1:]
    if len(s) == 3:
        return tuple((
            0x10 * int(c, 0x10) / 256
            for c in s
        ))
    elif len(s) == 6:
        return tuple((
            int(s[i * 2: (i + 1) * 2], 0x10) / 256
            for i in range(len(s) // 2)
        ))
    else:
        raise ValueError('invalid hex: {}'.format(s))


def parse_colors_hex(indexes_and_hexes):
    return [
        ColorPoint(index, hex_to_tuple(hex_s))
        for index, hex_s in indexes_and_hexes
    ]


# predefined palettes
###############################################################################

funny_rainbow = parse_colors_co_scss('''
$color1: rgba(249, 200, 14, 1);
$color2: rgba(248, 102, 36, 1);
$color3: rgba(234, 53, 70, 1);
$color4: rgba(102, 46, 155, 1);
$color5: rgba(67, 188, 205, 1);''')

barbie = parse_colors_co_scss('''
$color1: rgba(247, 237, 240, 1);
$color2: rgba(244, 203, 198, 1);
$color3: rgba(244, 175, 171, 1);
$color4: rgba(244, 238, 169, 1);
$color5: rgba(244, 244, 130, 1);''')

purple_haze = parse_colors_co_scss('''
$color1: rgba(110, 68, 255, 1);
$color2: rgba(184, 146, 255, 1);
$color3: rgba(244, 175, 171, 1);
$color4: rgba(255, 194, 226, 1);
$color5: rgba(239, 122, 133, 1);''')

red_death = parse_colors_co_scss('''
$color1: rgba(252, 68, 15, 1);
$color2: rgba(162, 0, 33, 1);
$color3: rgba(245, 47, 87, 1);
$color4: rgba(247, 157, 92, 1);
$color5: rgba(237, 237, 244, 1);''')

gabe_red = parse_colors_co_scss('''
$color1: rgba(88, 39, 7, 1);
$color2: rgba(162, 0, 33, 1);
$color3: rgba(255, 75, 62, 1);
$color4: rgba(255, 178, 15, 1);
$color5: rgba(255, 229, 72, 1);''')

super_red = parse_colors_co_scss('''
$color1: rgba(196, 30, 61, 1);
$color2: rgba(125, 17, 40, 1);
$color3: rgba(255, 44, 85, 1);
$color4: rgba(60, 9, 25, 1);
$color5: rgba(226, 41, 79, 1);''')

ultra_rainbows = parse_colors_co_scss('''
$color1: rgba(4, 231, 98, 1);
$color2: rgba(245, 183, 0, 1);
$color3: rgba(255, 44, 85, 1);
$color4: rgba(0, 161, 228, 1);
$color5: rgba(137, 252, 0, 1);''')

earth_life = parse_colors_co_scss('''
$color1: rgba(79, 52, 90, 1);
$color2: rgba(89, 60, 143, 1);
$color3: rgba(143, 169, 152, 1);
$color4: rgba(156, 191, 167, 1);
$color5: rgba(201, 242, 153, 1);''')

# https://coolors.co/ffffff-ea7af4-b43e8f-6200b3-8451ad
blueish_palette = parse_colors_co_scss('''
$color1: rgba(255, 255, 255, 1);
$color2: rgba(234, 122, 244, 1);
$color3: rgba(180, 62, 143, 1);
$color4: rgba(98, 0, 179, 1);
$color5: rgba(132, 81, 173, 1);''')

# https://coolors.co/7e5920-210f04-dc851f-621b00-f42c04
brownish_palette = parse_colors_co_scss('''
$color1: rgba(126, 89, 32, 1);
$color2: rgba(33, 15, 4, 1);
$color3: rgba(220, 133, 31, 1);
$color4: rgba(98, 27, 0, 1);
$color5: rgba(244, 44, 4, 1);''')

# https://coolors.co/ffffff-cb27ce-8a1a8c-401a8c-000000
white_violet = parse_colors_co_scss('''
$color1: rgba(255, 255, 255, 1);
$color2: rgba(203, 39, 206, 1);
$color3: rgba(138, 26, 140, 1);
$color4: rgba(64, 26, 140, 1);
$color5: rgba(0, 0, 0, 1);''')

coolors_rainbow = parse_colors_co_scss('''
$color1: rgba(31, 139, 248, 1);
$color2: rgba(237, 37, 78, 1);
$color3: rgba(222, 13, 146, 1);
$color4: rgba(208, 5, 118, 1);
$color5: rgba(249, 220, 92, 1);''')

just_greens = parse_colors_co_scss('''
$color1: rgba(56, 108, 11, 1);
$color2: rgba(56, 167, 0, 1);
$color3: rgba(49, 216, 67, 1);
$color4: rgba(4, 106, 56, 1);
$color5: rgba(62, 255, 139, 1);''')

quite_bright = parse_colors_co_scss('''
$color1: rgba(48, 69, 41, 1);
$color2: rgba(74, 103, 65, 1);
$color3: rgba(140, 112, 81, 1);
$color4: rgba(237, 180, 88, 1);
$color5: rgba(212, 212, 170, 1);''')

blue_purple = parse_colors_co_scss('''
$color1: rgba(202, 44, 146, 1);
$color2: rgba(127, 0, 255, 1);
$color3: rgba(0, 56, 168, 1);
$color4: rgba(129, 20, 83, 1);
$color5: rgba(159, 0, 197, 1);''')

black_violet = parse_colors_hex((
    (0, '000'),
    (0.3, '000'),
    (0.6, '418'),
    (1.0, '818'),
))

black_white = parse_colors_hex((
    (0, '000'),
    (1.0, 'FFF'),
))
