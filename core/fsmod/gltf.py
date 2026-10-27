"""Minimal binary glTF 2.0 (GLB) writer: geometry only (no materials), one primitive per mesh."""
import json
import struct


def _pad(b, fill=b'\0'):
    return b + fill * (-len(b) % 4)


def write_glb(meshes):
    """meshes: [{'name', 'positions': [[x, y, z]], 'normals', 'uvs': [[u, v]], 'uvs1'?, 'indices'}] -> GLB bytes.
    Each mesh becomes a node with the same name."""
    buf = bytearray()
    views, accessors, gl_meshes, nodes = [], [], [], []

    def add(data, component, type_, count, target, minmax=None):
        while len(buf) % 4:
            buf.append(0)
        views.append({'buffer': 0, 'byteOffset': len(buf), 'byteLength': len(data), 'target': target})
        buf.extend(data)
        acc = {'bufferView': len(views) - 1, 'componentType': component, 'count': count, 'type': type_}
        if minmax:
            acc['min'], acc['max'] = minmax
        accessors.append(acc)
        return len(accessors) - 1

    for m in meshes:
        pos, n = m['positions'], len(m['positions'])
        attrs = {'POSITION': add(b''.join(struct.pack('<3f', *p[:3]) for p in pos), 5126, 'VEC3', n, 34962,
                                 ([min(p[k] for p in pos) for k in range(3)], [max(p[k] for p in pos) for k in range(3)]))}
        if m.get('normals'):
            attrs['NORMAL'] = add(b''.join(struct.pack('<3f', *v) for v in m['normals']), 5126, 'VEC3', n, 34962)
        for key, attr in (('uvs', 'TEXCOORD_0'), ('uvs1', 'TEXCOORD_1')):
            if m.get(key):
                attrs[attr] = add(b''.join(struct.pack('<2f', *v[:2]) for v in m[key]), 5126, 'VEC2', n, 34962)
        idx = m['indices']
        big = max(idx) > 0xFFFF
        data = struct.pack(f'<{len(idx)}{"I" if big else "H"}', *idx)
        prim = {'attributes': attrs, 'indices': add(data, 5125 if big else 5123, 'SCALAR', len(idx), 34963), 'mode': 4}
        gl_meshes.append({'name': m['name'], 'primitives': [prim]})
        nodes.append({'name': m['name'], 'mesh': len(gl_meshes) - 1})

    doc = {'asset': {'version': '2.0', 'generator': 'fsmod'}, 'scene': 0,
           'scenes': [{'nodes': list(range(len(nodes)))}], 'nodes': nodes, 'meshes': gl_meshes,
           'accessors': accessors, 'bufferViews': views, 'buffers': [{'byteLength': len(_pad(bytes(buf)))}]}
    if not buf:  # no meshes: a valid empty scene (glTF forbids a 0-byte buffer)
        del doc['buffers'], doc['bufferViews'], doc['accessors'], doc['meshes']
        js = _pad(json.dumps(doc, separators=(',', ':')).encode(), b' ')
        return struct.pack('<4sII', b'glTF', 2, 20 + len(js)) + struct.pack('<I4s', len(js), b'JSON') + js
    js = _pad(json.dumps(doc, separators=(',', ':')).encode(), b' ')
    bin_ = _pad(bytes(buf))
    total = 12 + 8 + len(js) + 8 + len(bin_)
    return (struct.pack('<4sII', b'glTF', 2, total) + struct.pack('<I4s', len(js), b'JSON') + js +
            struct.pack('<I4s', len(bin_), b'BIN\0') + bin_)
