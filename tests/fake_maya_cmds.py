"""A minimal fake of the subset of maya.cmds used by maya_worker.py, enough
to unit-test the audit algorithms without a real Maya installation.

This is NOT a Maya emulator - it models just enough of a simple polygon
scene graph (transforms/shapes/history nodes/cameras) to drive the counting
logic in maya_worker.py. Real Maya API quirks (exact polySelectConstraint
behaviour, polyInfo output formatting across versions) can only be verified
against a real mayapy - see build brief section 6.
"""
from __future__ import annotations


class FakeCmds:
    def __init__(self):
        # scene graph: transform -> {"shape": str|None, "type": str,
        # "visibility": bool, "history": [nodeNames], "ngon_faces": int,
        # "bbox": (xmin,ymin,zmin,xmax,ymax,zmax), "face_count": int}
        # _scene_template models "what's on disk" - file(open=True) loads it
        # into self.objects, mimicking a real file open. file(new=True)
        # clears self.objects (an empty in-memory scene) without touching
        # the template, exactly like a real "New Scene" does not delete
        # the file on disk.
        self._scene_template: dict[str, dict] = {}
        self.objects: dict[str, dict] = {}
        self.selection: list[str] = []
        self._select_mode_component = False
        self._select_type_face = False
        self._constraint_active = False
        self.file_opened = None
        self.deleted = []

    # --- scene setup helpers used by tests, not part of the real API ---
    # Populate both the "live" scene (for tests that call helper functions
    # directly) and the on-disk template (for tests that go through
    # audit_model_file, which does file(new=True) then file(open=True)).
    def add_mesh(self, name, ngon_faces=0, face_count=6, bbox=(0, 0, 0, 1, 1, 1),
                 history=None, visibility=True):
        entry = {
            "type": "mesh", "visibility": visibility,
            "history": history or [], "ngon_faces": ngon_faces,
            "bbox": bbox, "face_count": face_count,
        }
        self._scene_template[name] = entry
        self.objects[name] = dict(entry)

    def add_camera(self, name):
        entry = {"type": "camera", "visibility": True, "history": []}
        self._scene_template[name] = entry
        self.objects[name] = dict(entry)

    def add_image_plane(self, name):
        entry = {"type": "imagePlane", "visibility": True, "history": []}
        self._scene_template[name] = entry
        self.objects[name] = dict(entry)

    # --- faked subset of maya.cmds ---
    def file(self, *args, **kwargs):
        if kwargs.get("new"):
            self.objects = {}
            self.file_opened = None
            return None
        if kwargs.get("query") and kwargs.get("reference"):
            return []
        if args and kwargs.get("open"):
            self.objects = {k: dict(v) for k, v in self._scene_template.items()}
            self.file_opened = args[0]
            return args[0]
        return None

    def ls(self, *args, **kwargs):
        node_type = kwargs.get("type")
        if node_type == "mesh":
            return [f"{n}Shape" for n, o in self.objects.items() if o["type"] == "mesh"]
        if node_type == "camera":
            return [f"{n}Shape" for n, o in self.objects.items() if o["type"] == "camera"]
        if node_type == "imagePlane":
            return [n for n, o in self.objects.items() if o["type"] == "imagePlane"]
        if kwargs.get("selection"):
            return list(self.selection)
        return list(self.objects.keys())

    def listRelatives(self, node, **kwargs):
        base = node.replace("Shape", "")
        if kwargs.get("parent"):
            return [base] if base in self.objects else []
        if kwargs.get("shapes"):
            return [f"{base}Shape"] if base in self.objects else []
        return []

    def polyEvaluate(self, *args, **kwargs):
        if kwargs.get("triangle"):
            return sum(o.get("face_count", 0) for o in self.objects.values() if o["type"] == "mesh")
        if kwargs.get("face") and args:
            node = args[0]
            return self.objects.get(node, {}).get("face_count", 0)
        return 0

    def select(self, *args, **kwargs):
        if kwargs.get("clear"):
            self.selection = []
            return
        names = args[0] if args and isinstance(args[0], list) else list(args)
        if kwargs.get("replace") or kwargs.get("add") is None:
            self.selection = list(names)

    def changeSelectMode(self, **kwargs):
        self._select_mode_component = bool(kwargs.get("component"))

    def selectType(self, **kwargs):
        self._select_type_face = bool(kwargs.get("polymeshFace"))

    def polySelectConstraint(self, **kwargs):
        if kwargs.get("mode") == 0:
            self._constraint_active = False
            return
        self._constraint_active = True
        # Simulate: expand current transform selection into ngon faces only
        expanded = []
        for name in self.selection:
            n = self.objects.get(name.replace("Shape", ""), {})
            count = n.get("ngon_faces", 0)
            expanded.extend(f"{name}.f[{i}]" for i in range(count))
        self.selection = expanded

    def listHistory(self, node, **kwargs):
        base = node.replace("Shape", "")
        obj = self.objects.get(base, {})
        return list(obj.get("history", [])) + [f"{base}Shape"]

    def nodeType(self, node):
        if node.endswith("Shape"):
            return "mesh"
        return "polyModifier"  # anything else in fake history is a modifier

    def getAttr(self, attr):
        node, prop = attr.rsplit(".", 1)
        obj = self.objects.get(node, {})
        if prop == "visibility":
            return obj.get("visibility", True)
        return None

    def exactWorldBoundingBox(self, node):
        return list(self.objects[node]["bbox"])

    def duplicate(self, node, **kwargs):
        dup_name = kwargs.get("name", f"{node}_dup")
        self.objects[dup_name] = dict(self.objects[node])
        return [dup_name]

    def polyNormal(self, *args, **kwargs):
        return None

    def polyInfo(self, component, **kwargs):
        # Always report a consistent outward normal; individual tests
        # override this method when they need to simulate an inversion.
        return ["FACE_NORMAL      0: 0.000000 1.000000 0.000000"]

    def delete(self, node):
        self.deleted.append(node)
        self.objects.pop(node, None)
