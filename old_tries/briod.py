import xml.etree.ElementTree as ET
from pprint import pprint
from random import randint

from tinycss2 import parse_one_component_value, parse_declaration_list
from tinycss2 import parse_component_value_list, serialize
from tinycss2.ast import NumberToken as Num, URLToken as Url, HashToken as HT
from tinycss2.ast import DimensionToken as Dim, LiteralToken as Lit

def interpolate(src, tgt, v):
    if type(src) != type(tgt):
        print(src, tgt)
        raise ValueError(f'{type(src)} =/=> {type(tgt)}')
    if isinstance(src, Num):
        v = round((src.value*(1-v) + tgt.value*v), 6)
        return Num(0, 0, v, v, str(v))
    elif isinstance(src, Dim):
        if src.unit != tgt.unit:
            raise ValueError(f'{src.unit} =/=> {tgt.unit}')
        v = round((src.value*(1-v) + tgt.value*v), 6)
        return Dim(0, 0, v, v, str(v), src.unit)
    elif isinstance(src, HT):
        a, b  = src.value, tgt.value
        print(a, b)
        try:
            int(src.value, 16)
            int(tgt.value, 16)
        except ValueError:
            return src
        v = ''.join(format(int(int(b[i:i+2], 16)*(v)+
                                int(a[i:i+2], 16)*(1-v)), 'x').zfill(2)
                    for i in range(0,6,2))
        return HT(0, 0, v, 0)
    elif isinstance(src, list):
        return [round((a*(1-v)+b*v),6) if isinstance(a, (float, int)) else a 
                for a,b in zip(src, tgt)]
    else:
        raise ValueError(f'Unknow type {type(src)}')

class Node:
    
    def __init__(self, node, ids):
        self.node, self.ids, self.myid = node, ids, node.attrib['id']
        self.name = node.tag.partition('}')[2]
        self.attrs = {key: el for key, value in node.attrib.items()
                      if isinstance((el := parse_one_component_value(value)),
                                    (Num, HT, Dim, Url))}
        style = {rule.name: rule.value[0] for rule in
                 parse_declaration_list(node.get('style', ''))}
        self.style = {key: value for key, value in style.items()
                      if isinstance(value, (Num, HT, Dim))}
        self.links = {key: value.value.lstrip('#') for key, value in style.items()
                      if isinstance(value, Url)}
        self.trans = {rule.name: [v.value for v in rule.arguments]
                      for rule in parse_component_value_list(
                          node.get('transform', ''))
                      if any(isinstance(v, (Num, Dim)) for v in rule.arguments)}
        self.blur = 0
        if 'filter' in self.links:
            if (myfilter := ids.get(self.links['filter'], None)):
                for element in myfilter.iter():
                    if 'feGaussianBlur' in element.tag:
                        self.blur = float(element.attrib['stdDeviation'])
                        break
        print()
        print(node.attrib['id'], self.name)
        pprint(self.attrs)
        pprint(self.style)
        pprint(self.links)
        pprint(self.trans)
        print('blur:', self.blur)
        print()
    
    def inter(self, other, v):
        print('DIFFING')
        # Name
        if self.name != other.name:
            if self.name == 'circle' and other.name == 'ellipse':
                self.node.tag, self.name = 'ellipse', 'ellipse'
                self.attrs['rx'], self.attrs['ry'] = (self.attrs['r'],)*2
                del self.attrs['r']
            elif self.name == 'ellipse' and other.name == 'circle':
                other.node.tag, other.name = 'ellipse', 'ellipse'
                other.attrs['rx'], other.attrs['ry'] = (other.attrs['r'],)*2
                del other.attrs['r']
            else:
                raise ValueError(f'{self.name} =/=> {other.name}')
        
        print('     attrs     ')
        # Attrs
        for key in self.attrs.keys() | other.attrs.keys():
            mine, theirs = self.attrs.get(key, None), other.attrs.get(key, None)
            if not theirs:
                print(f'{self.myid}.{key} =/=> {other.myid}.???   ...assuming 0 ********')
                theirs = mine
            if not mine:
                print(f'{self.myid}.??? =/=> {other.myid}.{key}   ...assuming 0 ********')
                mine = theirs
            inter = interpolate(mine, theirs, v)
            self.node.attrib[key] = (inter.representation if not isinstance(inter, HT)
                                     else '#'+inter.value)
            print(key, mine, theirs, interpolate(mine, theirs, v))
        
        print('     style     ')
        # Style
        changes = {}
        for key in self.style.keys() | other.style.keys():
            mine, theirs = self.style.get(key, None), other.style.get(key, None)
            if not theirs:
                print(f'{self.myid}.{key} =/=> {other.myid}.???   ...assuming 0 ********')
                theirs = mine
            if not mine:
                print(f'{self.myid}.??? =/=> {other.myid}.{key}   ...assuming 0 ********')
                mine = theirs
            changes[key] = interpolate(mine, theirs, v)
            print(key, mine, theirs, interpolate(mine, theirs, v))
        rules = parse_declaration_list(self.node.get('style', ''))
        for rule in rules:
            if rule.name in changes:
                rule.value = [changes[rule.name]]
        self.node.attrib['style'] = serialize(rules)
        
        print('     links     ')
        # Links
        for key in self.links.keys() & other.links.keys():
            if (mine := self.ids[self.links[key]]) and (their := other.ids[other.links[key]]):
                Node(mine, self.ids).inter(Node(their, other.ids), v)
        
        print('     trans     ')
        # Trans
        changes = {} 
        for key in self.trans.keys() | other.trans.keys():
            mine, theirs = self.trans.get(key, None), other.trans.get(key, None)
            if not theirs:
                print(f'{self.myid}.{key} =/=> {other.myid}.???   ...assuming 0 ********')
                theirs = [0 if isinstance(x, (float, int)) else x for x in mine]
            if not mine:
                print(f'{self.myid}.??? =/=> {other.myid}.{key}   ...assuming 0 ********')
                mine = [0 if isinstance(x, (float, int)) else x for x in theirs]
            changes[key] = interpolate(mine, theirs, v)
            print(mine, theirs, changes[key])
        rules = parse_component_value_list(self.node.attrib.get('transform', ''))
        for rule in rules:
            if rule.name in changes:
                rule.arguments = [Lit(0, 0, ''.join(str(a) for a in changes[rule.name]))]
        self.node.attrib['transform'] = serialize(rules)
        
        # Blur
        print('     blur     ')
        avgblur = round((self.blur*(1-v) + other.blur*v), 6)
        print(avgblur)
        if avgblur != 0 and self.blur == 0:
            name = 'filter' + str(randint(0,10000))
            self.node.attrib['style'] += f'filter:url(#{name});'
            for n in self.ids['root']:
                if n.tag.endswith('defs'):
                    defs = n
                    break
            else:
                raise ValueError('Cant create defs yet')
            ET.SubElement(defs, 'filter', id='name').text = f"""<feGaussianBlur
         inkscape:collect="always"
         stdDeviation="{avgblur}"
         id="feGaussianBlur{name}" />"""
        

ET.register_namespace("", "http://www.w3.org/2000/svg")
svg = (tree := ET.parse('drawingb.svg')).getroot()
ids = {node.attrib['id']: node for node in svg.iter() if 'id' in node.attrib}
ids['root'] = svg
nodes = {name: Node(el, ids) for name, el in ids.items()}
svg2 = (treeb := ET.parse('drawing.svg')).getroot()
ids2 = {node.attrib['id']: node for node in svg2.iter() if 'id' in node.attrib}
ids2['root'] = svg2
nodes2 = {name: Node(el, ids2) for name, el in ids2.items()}
for key in nodes.keys() & nodes2.keys():
    nodes[key].inter(nodes2[key], 1)
tree.write('drawing_test_output.svg')
