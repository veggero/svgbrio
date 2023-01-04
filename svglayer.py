from dataclasses import dataclass
from typing import List, Dict, Union, Tuple, Optional
import xml.etree.ElementTree as ET
from pprint import pprint
from random import randint

import tinycss2
from tinycss2 import parse_declaration_list, parse_component_value_list
import tinycss2.color3
import webcolors
from svg.path import parse_path, Path
import pyvips

def mix(a, b, v):
    if type(a) == type(b) == Dimension: return a.mix(b, v)
    return a*(1-v) + b*v

def strmix(a, b, v):
    if len(a) < len(b):
        a = a.ljust(len(b))
    elif len(a) > len(b):
        b = b.ljust(len(a))
    diff = [i for i, (x, y) in enumerate(zip(a, b)) if x!=y]
    diff = diff[:int(v*len(diff))]
    a = ''.join(cb if i in diff else ca for i, (ca, cb) in enumerate(zip(a, b)))
    return a

def objectify(node, nodes):
    objs = {'linearGradient': LinearGradient,
            'radialGradient': RadialGradient,
            'rect': Rect,
            'circle': Ellipse,
            'ellipse': Ellipse,
            'text': Text,
            'line': Line,
            'polyline': PolyLine,
            'path': Path}
    if not node.name in objs: return None
    return objs[node.name](node, nodes)

@dataclass(frozen=True)
class Dimension:
    value: int
    unit: str

    def mix(self, other, value: int):
        assert self.unit == other.unit
        return Dimension(mix(self.value, other.value, value), self.unit)

    def __str__(self): return f'{self.value}{self.unit}'

@dataclass(frozen=True)
class Link:
    to: str

    def __str__(self): return f'url(#{self.to})'

@dataclass(frozen=True)
class Color:
    r: int
    g: int
    b: int
    alpha: int = 1

    def mix(self, other, value: int):
        return Color(int(mix(self.r, other.r, value)),
                     int(mix(self.g, other.g, value)),
                     int(mix(self.b, other.b, value)),
                     mix(self.alpha, other.alpha, value),)

    def __str__(self): return f'#{self.r:02x}{self.g:02x}{self.b:02x}'
    #def __str__(self): return f'rgba({self.r}, {self.g}, {self.b}, {self.alpha})'

@dataclass(frozen=True)
class Function:
    name: str
    arguments: Tuple

    def __str__(self):
        return f'{self.name}({", ".join(map(str, self.arguments))})'

@dataclass(frozen=True)
class SorryWhat:
    content: str

    def __str__(self): return self.content

class Node:

    def __init__(self, xmln):
        self.xmln = xmln
        self.name = xmln.tag.partition('}')[2]
        self.properties = {}
        self._properties_loc = {}
        for key, value in self.xmln.attrib.items():
            if key in ('style', 'id'): continue
            css = self.parse_css(tinycss2.parse_component_value_list(value))
            if key not in ('transform', 'gradientTransform') and len(css)==1:
                css = css[0]
            self.properties[key] = css
            self._properties_loc[key] = 'attrib'
        declarations = parse_declaration_list(self.xmln.attrib.get('style', ''))
        for decl in self.clean(declarations):
            css = self.parse_css(decl.value)
            if decl.name not in ('transform', 'gradientTransform') and len(css)==1:
                css = css[0]
            self.properties[decl.name] = css
            self._properties_loc[decl.name] = 'style'

    def __setitem__(self, key, value):
        if key not in self.properties:
            self._properties_loc[key] = 'attrib'
        self.properties[key] = value
        if not isinstance(value, list): value = [value]
        value = ' '.join(map(str, value))
        if self._properties_loc[key] == 'attrib':
            self.xmln.attrib[key] = str(value)
        elif self._properties_loc[key] == 'style':
            css = self.xmln.attrib['style'].split(';')
            rule = next(i for i in range(len(css))
                        if css[i].split(':')[0].strip() == key)
            css[rule] = css[rule].split(':')[0] + ':' + str(value)
            self.xmln.attrib['style'] = ';'.join(css)

    @classmethod
    def parse_css(self, el):
        if isinstance(el, list):
            return tuple(map(self.parse_css, self.clean(el)))
            el = self.clean(el)
        if (c := tinycss2.color3.parse_color(el)):
            return Color(c.red*255, c.green*255, c.blue*255, c.alpha)
        if el.type == 'number': return el.value
        elif el.type == 'dimension': return Dimension(el.value, el.unit)
        elif el.type == 'percentage': return Dimension(el.value, '%')
        elif el.type == 'url' and el.value.startswith('#'):
            return Link(el.value.lstrip('#'))
        elif el.type == 'function':
            return Function(el.name, self.parse_css(el.arguments))
        return SorryWhat(tinycss2.serialize([el]))

    @classmethod
    def clean(self, rules):
        return [rule for rule in rules if rule.type not in
                ('comment', 'whitespace', 'literal')]

@dataclass(frozen=True)
class Stop:
    offset: int
    color: Color

    def mix(self, other, value: int):
        return Stop(mix(self.offset, other.offset, value),
                    self.color.mix(other.color, value))

@dataclass(frozen=True)
class Point:
    x: int
    y: int

    def mix(self, other, value: int):
        return Point(mix(self.x, other.x, value), mix(self.y, other.y, value))

@dataclass(frozen=True)
class Transforms:
    translate: Tuple[int] = (0, 0)
    rotate: int = (0, 0, 0)
    skew: Tuple[int] = (0, 0)
    scale: Tuple[int] = (1, 1)
    matrix: Tuple[int] = (0, 0, 0, 0, 0, 0)

    @staticmethod
    def mix_tuple(one, two, value):
        return tuple(mix(a, b, value) for a, b in zip(one, two))

    def mix(self, other, value: int):
        return Transforms(self.mix_tuple(self.translate, other.translate, value),
                          self.mix_tuple(self.rotate, other.rotate, value),
                          self.mix_tuple(self.skew, other.skew, value),
                          self.mix_tuple(self.scale, other.scale, value),
                          self.mix_tuple(self.matrix, other.matrix, value),)

class Gradient:

    def __init__(self, node: Node, nodes: Dict[str, Node]):
        self.node, self.nodes = node, nodes

    def mix(self, other, value: int):
        self.transforms = self.transforms.mix(other.transforms, value)
        assert len(self.stops) == len(other.stops)
        self.stops = tuple(s.mix(o, value) for s, o in zip(self.stops, other.stops))
        return self

    @property
    def transforms(self) -> Transforms:
        return Drawable.read_transforms(self, 'gradientTransform')

    @transforms.setter
    def transforms(self, value: Transforms):
        Drawable.write_transforms(self, 'gradientTransform', value)

    @property
    def stops(self) -> Tuple[Stop]:
        stops = []
        for element in self.node.xmln:
            if not 'stop' in element.tag: continue
            stop = Node(element)
            color = stop.properties['stop-color']
            opacity = stop.properties.get('stop-opacity', color.alpha)
            stops.append(Stop(stop.properties['offset'],
                              Color(color.r, color.g, color.b, opacity)))
        if stops: return tuple(stops)
        xlink = '{http://www.w3.org/1999/xlink}'
        if f'{xlink}href' not in self.node.properties: return ()
        myclass = Gradient(self.nodes[self.node.properties[f'{xlink}href'].content.lstrip('#')], self.nodes)
        return myclass.stops

    @stops.setter
    def stops(self, value: Tuple[Stop]):
        for child in list(self.node.xmln):
            self.node.xmln.remove(child)
        for stop in value:
            stopel = Node(ET.SubElement(self.node.xmln, 'stop'))
            stopel['offset'] = stop.offset
            stopel['stop-color'] = stop.color
            stopel['stop-opacity'] = stop.color.alpha

    stops: Tuple[Stop]

class LinearGradient(Gradient):

    def mix(self, other, value: int):
        self.origin = self.origin.mix(other.origin, value)
        self.target = self.target.mix(other.target, value)
        super().mix(other, value)
        return self

    @property
    def origin(self) -> Point:
        return Point(self.node.properties.get('x1', 0),
                     self.node.properties.get('y1', 0))

    @origin.setter
    def origin(self, value: Point):
        self.node['x1'], self.node['y1'] = value.x, value.y


    @property
    def target(self) -> Point:
        return Point(self.node.properties.get('x2', 0),
                     self.node.properties.get('y2', 0))

    @target.setter
    def target(self, value: Point):
        self.node['x2'], self.node['y2'] = value.x, value.y

class RadialGradient(Gradient):

    def mix(self, other, value: int):
        self.center = self.center.mix(other.center, value)
        self.focal = self.focal.mix(other.focal, value)
        self.radius = mix(self.radius, other.radius, value)
        self.focal_radius = mix(self.focal_radius, other.focal_radius, value)
        super().mix(other, value)
        return self

    @property
    def center(self) -> Point:
        return Point(self.node.properties['cx'],
                     self.node.properties['cy'])

    @center.setter
    def center(self, value: Point):
        self.node['cx'] = value.x
        self.node['cy'] = value.y

    @property
    def focal(self) -> Point:
        return Point(self.node.properties.get('fx',0),
                     self.node.properties.get('fy',0))

    @focal.setter
    def focal(self, value: Point):
        self.node['fx'] = value.x
        self.node['fy'] = value.y

    @property
    def radius(self) -> Point:
        return self.node.properties['r']

    @radius.setter
    def radius(self, value: Point):
        self.node['r'] = value

    @property
    def focal_radius(self) -> Point:
        return self.node.properties.get('fr', 0)

    @focal_radius.setter
    def focal_radius(self, value: Point):
        self.node['fr'] = value

@dataclass(frozen=True)
class Stroke:
    color: Optional[Union[Color, LinearGradient, RadialGradient]]
    width: Optional[int] = 0

    def mix(self, other, value: int):
        assert type(self.color) == type(other.color)
        assert (self.color is None) == (other.color is None)
        assert (self.width is None) == (other.width is None)
        return Stroke(self.color.mix(other.color, value) if self.color else None,
                      mix(self.width, other.width, value) if self.width else None)

class Drawable:

    def __init__(self, node: Node, nodes: Dict[str, Node]):
        self.node, self.nodes = node, nodes

    def mix(self, other, value: int):
        assert type(self.fill) == type(other.fill)
        if self.fill:
            self.fill = self.fill.mix(other.fill, value)
        self.stroke = self.stroke.mix(other.stroke, value)
        self.blur = mix(self.blur, other.blur, value)
        self.transforms = self.transforms.mix(other.transforms, value)

    def read_color(self, color, opacity):
        c = self.node.properties.get(color, None)
        if isinstance(c, Color):
            co = self.node.properties.get(opacity, c.alpha)
            return Color(c.r, c.g, c.b, co)
        elif isinstance(c, Link):
            element = self.nodes[c.to]
            if element.name == 'linearGradient':
                return LinearGradient(element, self.nodes)
            elif element.name == 'radialGradient':
                return RadialGradient(element, self.nodes)
        return None

    def write_color(self, value, color, opacity):
        if isinstance(value, Color):
            self.node[color] = value
            self.node[opacity] = value.alpha
        elif isinstance(value, (LinearGradient, RadialGradient)):
            self.node[color] = Link(value.node.xmln.attrib['id'])

    @property
    def fill(self) -> Optional[Union[Color, LinearGradient, RadialGradient]]:
        return self.read_color('fill', 'fill-opacity')

    @fill.setter
    def fill(self, value: Union[Color, LinearGradient, RadialGradient]):
        self.write_color(value, 'fill', 'fill-opacity')

    @property
    def stroke(self) -> Stroke:
        return Stroke(self.read_color('stroke', 'stroke-opacity'),
                      self.node.properties.get('stroke-width', 0))

    @stroke.setter
    def stroke(self, value: Stroke):
        if value.color:
            self.write_color(value.color, 'stroke', 'stroke-opacity')
        if value.width:
            self.node['stroke-width'] = value.width

    @property
    def blur(self) -> int:
        if 'filter' not in self.node.properties: return 0
        self.filt = self.nodes[self.node.properties['filter'].to].xmln
        for element in self.filt.iter():
            if 'feGaussianBlur' not in element.tag: continue
            self.blurel = element
            return float(element.attrib['stdDeviation'])

    @blur.setter
    def blur(self, value: int):
        if not hasattr(self, 'blurel'):
            if value == 0: return
            defs = self.nodes['!defs']
            filterid = f'filter{randint(0, 10000)}'
            self.node['filter'] = Link(filterid)
            self.filt = ET.SubElement(defs.xmln, 'filter')
            self.filt.attrib['id'] = filterid
            self.nodes[filterid] = Node(self.filt)
            self.blurel = ET.SubElement(self.filt, 'feGaussianBlur')
        self.blurel.attrib['stdDeviation'] = str(value)
        self.filt.attrib['x'] = '-1'
        self.filt.attrib['y'] = '-1'
        self.filt.attrib['width'] = '3'
        self.filt.attrib['height'] = '3'

    @property
    def transforms(self) -> Transforms:
        return self.read_transforms('transform')

    def read_transforms(self, name):
        nodetransfs = self.node.properties.get(name, [])
        args = {'translate': (0, 0), 'rotate': (0, 0, 0), 'skewX': (0,),
                'skewY': (0,), 'scale': (1, 1), 'matrix': (1, 0, 0, 1, 0, 0)}
        args.update({t.name: t.arguments for t in nodetransfs
                     if t.name in args})
        args['skew'] = (args['skewX'][0], args['skewY'][0])
        del args['skewX'], args['skewY']
        if len(args['scale']) == 1:
            args['scale'] = (args['scale'][0],)*2
        if len(args['translate']) == 1:
            args['translate'] = (args['translate'][0],)*2
        if len(args['rotate']) == 1:
            args['rotate'] = (args['rotate'][0], 0, 0)
        return Transforms(**args)

    @transforms.setter
    def transforms(self, value):
        return self.write_transforms('transform', value)

    def write_transforms(self, name, value):
        args = {'translate': value.translate, 'rotate': value.rotate,
                'skewX': [value.skew[0]], 'skewY': [value.skew[1]],
                'scale': value.scale, 'matrix': value.matrix}
        self.node[name] = [Function(key, value) for key, value in args.items()]


class Rect(Drawable):

    def mix(self, other, value: int):
        self.position = self.position.mix(other.position, value)
        self.size = self.size.mix(other.size, value)
        self.roundness = self.roundness.mix(other.roundness, value)
        super().mix(other, value)

    @property
    def position(self) -> Point:
        return Point(self.node.properties.get('x', 0),
                     self.node.properties.get('y', 0))

    @position.setter
    def position(self, value: Point):
        self.node['x'], self.node['y'] = value.x, value.y

    @property
    def size(self) -> Point:
        return Point(self.node.properties['width'],
                     self.node.properties['height'])

    @size.setter
    def size(self, value: Point):
        self.node['width'] = value.x
        self.node['height'] = value.y

    @property
    def roundness(self) -> Point:
        return Point(self.node.properties.get('rx', 0),
                     self.node.properties.get('ry', 0))

    @roundness.setter
    def roundness(self, value: Point):
        self.node['rx'] = value.x
        self.node['ry'] = value.y

class Ellipse(Drawable):

    def mix(self, other, value: int):
        self.center = self.center.mix(other.center, value)
        self.radius = self.radius.mix(other.radius, value)
        super().mix(other, value)

    @property
    def center(self) -> Point:
        return Point(self.node.properties['cx'],
                     self.node.properties['cy'])

    @center.setter
    def center(self, value: Point):
        self.node['cx'] = value.x
        self.node['cy'] = value.y

    @property
    def radius(self) -> Point:
        if 'circle' == self.node.name:
            return Point(*[self.node.properties['r']]*2)
        return Point(self.node.properties['rx'],
                     self.node.properties['ry'])

    @radius.setter
    def radius(self, value: Point):
        if self.node.name == 'circle':
            self.node.xmln.tag = self.node.name = 'ellipse'
        self.node['rx'] = value.x
        self.node['ry'] = value.y

class Text(Drawable):

    def mix(self, other, value: int):
        self.text = strmix(self.text, other.text, value)
        self.position = self.position.mix(other.position, value)
        self.font_size = mix(self.font_size, other.font_size, value)
        super().mix(other, value)

    @property
    def position(self) -> Point:
        return Point(self.node.properties.get('x', 0),
                     self.node.properties.get('y', 0))

    @position.setter
    def position(self, value: Point):
        self.node['x'], self.node.properties['y'] = value.x, value.y

    @property
    def font_size(self) -> int:
        return self.node.properties.get('font-size', 0)

    @font_size.setter
    def font_size(self, value: int):
        self.node['font-size'] = value

    @property
    def text(self) -> str:
        return self.node.xmln.text

    @text.setter
    def text(self, value: str):
        self.node.xmln.text = value

class Line(Drawable):

    def mix(self, other, value: int):
        self.origin = self.origin.mix(other.origin, value)
        self.target = self.target.mix(other.target, value)
        super().mix(other, value)

    @property
    def origin(self) -> Point:
        return Point(self.node.properties.get('x1', 0),
                     self.node.properties.get('y1', 0))

    @origin.setter
    def origin(self, value: Point):
        self.node['x1'], self.node['y1'] = value.x, value.y


    @property
    def target(self) -> Point:
        return Point(self.node.properties.get('x2', 0),
                     self.node.properties.get('y2', 0))

    @target.setter
    def target(self, value: Point):
        self.node['x2'], self.node['y2'] = value.x, value.y

class PolyLine(Drawable):

    def mix(self, other, value: int):
        super().mix(other, value)
        return #TODO

    @property
    def points(self) -> Tuple[Point]:
        points = self.node.xmln.attrib['points'].split()
        return tuple(Point(*map(int, p.split(','))) for p in points)

    @points.setter
    def points(self, value: Tuple[Point]):
        self.node.xmln.attrib['points'] = ' '.join(f'{p.x},{p.y}' for p in value)

class Path(Drawable):

    def mix(self, other, value: int):
        super().mix(other, value)
        return #TODO

    @property
    def instructions(self) -> Path:
        return parse_path(self.node.xmln.attrib['d'])

    @instructions.setter
    def instructions(self, value: Path):
        self.node.xmln.attrib['d'] = value.d()

ET.register_namespace("", "http://www.w3.org/2000/svg")
for i in range(101):
    svg = (tree := ET.parse('drawingb.svg')).getroot()
    svg2 = ET.parse('drawing.svg').getroot()
    ids = {node.attrib['id']: Node(node) for node in svg.iter() if 'id' in node.attrib}
    ids2 = {node.attrib['id']: Node(node) for node in svg2.iter() if 'id' in node.attrib}
    ids['!defs'] = ids['defs2']
    ids2['!defs'] = ids2['defs2']
    for key in ids.keys() & ids2.keys():
        if (obj := objectify(ids[key], ids)) and isinstance(obj, Drawable):
            print(key)
            obj.mix(objectify(ids2[key], ids2), i/100)
    tree.write(f'out/.svg/{i:03}.svg')
    pyvips.Image.new_from_file(f'out/.svg/{i:03}.svg').write_to_file(f'out/{i:03}.png')

