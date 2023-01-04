import xml.etree.ElementTree as ET
from pprint import pprint

import tinycss2
from tinycss2.ast import NumberToken as Num, URLToken as URL, HashToken as HT
import pyvips
import easing_functions

ET.register_namespace("", "http://www.w3.org/2000/svg")

def is_number(x):
    try: return float(x)
    except ValueError: return False

class Diff:
    
    def __init__(self, attrs, style, trans):
        self.attrs, self.style, self.trans = attrs, style, trans
    
    @staticmethod
    def interpolate(b, a, v):
        if isinstance(b, str):
            return HT(0, 0, 
                      format(int(int(b[:2], 16)*(1-v)+int(a[:2], 16)*v), 'x').zfill(2)+
                      format(int(int(b[2:4], 16)*(1-v)+int(a[2:4], 16)*v), 'x').zfill(2)+
                      format(int(int(b[4:], 16)*(1-v)+int(a[4:], 16)*v), 'x').zfill(2)
                      , 0)
        if isinstance(b, list):
            return [Diff.interpolate(x, y, v) for x, y in zip(b, a)]
        if isinstance(b, (int, float)):
            return Num(0, 0, 0, (value := b*(1-v)+a*v), str(value))
    
    def apply(self, node, progress):
        for key, value in self.attrs.items():
            node.attrib[key] = self.interpolate(*value, progress).representation
        
        rules = tinycss2.parse_declaration_list(node.attrib.get('style', ''))
        for rule in rules:
            if rule.name not in self.style: continue
            rule.value = [self.interpolate(*self.style[rule.name], progress)]
        node.attrib['style'] = tinycss2.serialize(rules)
        
        rules = tinycss2.parse_component_value_list(node.attrib.get('transform', ''))
        done = set()
        for rule in rules:
            if rule.name not in self.trans: continue
            done.add(rule.name)
            rule.arguments = self.interpolate(*self.trans[rule.name], progress)
        for key, value in self.trans.items():
            if key in done: continue
            value = self.interpolate(*value, progress)
            rules.append(tinycss2.astFunctionBlock(0, 0, key, value))
        node.attrib['transform'] = tinycss2.serialize(rules).replace('/**/', ',')
    
    def __repr__(self):
        return f'{self.attrs} {self.style} {self.trans}'
    
    def __bool__(self):
        return bool(self.attrs or self.style or self.trans)

class Properties:
    
    defaults = {
        'trans': {
            'matrix': [0, 0, 0, 0, 0, 0],
            'rotate': [0],
            'translate': [0, 0]
        },
        'style': {
            'opacity': 1
        },
        'attrs': {
            'stdDeviation': 0
        }
    }
    
    def __init__(self, node):
        self.attrs = {key: el for key, value in node.attrib.items()
                      if (el := is_number(value))}
        style = {rule.name: rule.value[0]
                 for rule in tinycss2.parse_declaration_list(
                     node.get('style', ''))}
        self.style = {key: value.value
                      for key, value in style.items()
                      if isinstance(value, (Num, HT))}
        self.links = {key: value.value.lstrip('#')
                      for key, value in style.items()
                      if isinstance(value, URL)}
        self.trans = {rule.name: [v.value for v in rule.arguments]
                      for rule in tinycss2.parse_component_value_list(
                          node.get('transform', ''))
                      if all(isinstance(v, Num) for v in rule.arguments)}
        self.attrs = {**self.defaults['attrs'], **self.attrs}
        self.style = {**self.defaults['style'], **self.style}
        self.trans = {**self.defaults['trans'], **self.trans}
    
    @staticmethod
    def dict_diff(a, b):
        return {key: (a[key], b[key]) 
                for key in a.keys() & b.keys() if a[key]!=b[key]}
    
    def __add__(self, other):
        "Checks for equivalent links"
        return {(a, b) for link in self.links.keys() & other.links.keys()
                if (a := self.links[link]) != (b := other.links[link])}
    
    def __sub__(self, other):
        "Checks for different values"
        return Diff(
            self.dict_diff(self.attrs, other.attrs),
            self.dict_diff(self.style, other.style),
            self.dict_diff(self.trans, other.trans)
            )

def svg_properties(svg):
    return {node.attrib['id']: Properties(node)
            for node in svg.iter() if 'id' in node.attrib}

def make_diff(before, after):
    common = before.keys() & after.keys()
    replacements = {el for key in common for el in before[key]+after[key]}
    nbefore, nafter = before.copy(), after.copy()
    for (one, two) in replacements:
        print(one, two)
        print(one in before, one in after)
        print(two in before, two in after)
        nbefore[two] = before[one]
        nafter[one] = after[two]
    before, after = nbefore, nafter
    common = before.keys() & after.keys()
    return {key: diff for key in common if (diff := before[key]-after[key])}

def apply_diff(svg, diff, progress):
    for el in svg.iter():
        if el.attrib.get('id', '') not in diff: continue
        diff[el.attrib['id']].apply(el, progress)

before = svg_properties(ET.parse('drawing.svg').getroot())
after = svg_properties(ET.parse('drawingb.svg').getroot())
diff = make_diff(before, after)
tree = ET.parse('drawing.svg')
for i in range(100):
    print(i)
    apply_diff(tree, diff, i/100)
    tree.write(f'out/.svg/{i}.svg')
    pyvips.Image.new_from_file(f'out/.svg/{i}.svg').write_to_file(f'out/{i:03}.png')
