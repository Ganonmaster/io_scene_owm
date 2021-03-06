import os
from math import radians

from . import read_owmdl
from . import import_owmat
from . import owm_types
from mathutils import *
from . import bpyhelper
import bpy, bpy_extras, mathutils, bmesh, random, collections

root = ''
settings = None
data = None
rootObject = None
blenderBoneNames = []

def newBoneName():
    global blenderBoneNames
    blenderBoneNames = []
def addBoneName(newName):
    global blenderBoneNames
    blenderBoneNames += [newName]
def getBoneName(originalIndex):
    if originalIndex < len(blenderBoneNames):
        return blenderBoneNames[originalIndex]
    else:
        return None

def fixLength(bone):
    default_length = 0.005
    if bone.length == 0:
        bone.tail = bone.head - Vector((0, .001, 0))
    if bone.length < default_length:
        bone.length = default_length

def tempCreateArmature(armature_name):
    if bpy.context.active_object:
        bpy.ops.object.mode_set(mode='OBJECT',toggle=False)
    a = bpy.data.objects.new(armature_name,bpy.data.armatures.new(armature_name))
    a.show_x_ray = True
    a.data.draw_type = 'STICK'
    bpy.context.scene.objects.link(a)
    for i in bpy.context.selected_objects: i.select = False #deselect all objects
    a.select = True
    bpy.context.scene.objects.active = a
    bpy.ops.object.mode_set(mode='OBJECT')

    return a

def importRefposeArmature(autoIk):
    a = tempCreateArmature("skeletonJeff")
    a.data.vs.implicit_zero_bone = False
    # todo: ^ needed?
    boneIDs = {}  # temp

    newBoneName()
    def addBone(num,name):
        bone = a.data.edit_bones.new(name)
        addBoneName(name)
        bone.tail = 0,5,0 # Blender removes zero-length bones
        bone.tail = 0,1,0 # Blender removes zero-length bones
        bone.tail = 0,0.005,0
        # fixLength(bone)
        boneIDs[num] = bone.name
        return bone
    
    bpy.ops.object.mode_set(mode='EDIT',toggle=False)
    index = 0
    for bone in data.refpose_bones:
        addBone(index,bone.name)
        index += 1
    
    bpy.ops.object.mode_set(mode='EDIT', toggle=False)

    index = 0
    for bone in data.refpose_bones:
        if bone.parent != -1:
            a.data.edit_bones[index].parent = a.data.edit_bones[bone.parent]
        index += 1

    bpy.context.scene.objects.active = a
    bpy.ops.object.mode_set(mode='POSE')

    # sect 2: get frame
    index = 0
    for refpose_bone in data.refpose_bones:
        pos = Vector([refpose_bone.pos[0], refpose_bone.pos[1], refpose_bone.pos[2]])
        rot = Euler([refpose_bone.rot[0], refpose_bone.rot[1], refpose_bone.rot[2]])
        # rot = wxzy(refpose_bone.rot).to_matrix().to_4x4()  # maybe use existing def?
        bone = a.pose.bones[getBoneName(index)]
        bone.matrix_basis.identity()
        bone.matrix = Matrix.Translation(pos) * rot.to_matrix().to_4x4()
        index += 1

    # sect 3: apply
    bpy.ops.pose.armature_apply()
    
    bpy.ops.object.mode_set(mode='OBJECT')
    a.data.use_auto_ik = autoIk
    return a
    

# rewrite me
def importArmature(autoIk):
    bones = data.bones
    armature = None
    if len(bones) > 0:
        armData = bpy.data.armatures.new("Armature")
        armData.draw_type = 'STICK'
        armature = bpy.data.objects.new("Armature", armData)
        armature.show_x_ray = True

        bpyhelper.scene_link(armature)

        bpyhelper.scene_active_set(armature)
        bpy.ops.object.mode_set(mode='EDIT')

        newBoneName()
        
        for bone in bones:
            bbone = armature.data.edit_bones.new(bone.name)
            addBoneName(bbone.name)
            # warning: matrix bugged.
            mpos = Matrix.Translation(xzy(bone.pos))
            mrot = wxzy(bone.rot).to_matrix().to_4x4()
            m = mpos * mrot
            
            bbone.matrix = m
                
            fixLength(bbone)
            
        for i, bone in enumerate(bones):
            if bone.parent > -1:
                bbone = armData.edit_bones[i]
                bbone.parent = armature.data.edit_bones[bone.parent]

        bpyhelper.select_obj(armature, True)
        bpy.ops.object.mode_set(mode='OBJECT')
        armature.data.use_auto_ik = autoIk
    return armature

def euler(rot): return Euler(rot[0:3])

def xzy(pos): return Vector(pos)

def wxzy(rot): return Quaternion(rot[0:3], rot[3])

def segregate(vertex):
    pos = []
    norms = []
    uvs = []
    boneData = []
    for vert in vertex:
        pos += [xzy(vert.position)]
        norm = Vector(vert.normal).normalized()
        norm[0] = -norm[0]
        norm[1] = -norm[1]
        norm[2] = -norm[2]
        norms += [norm]
        uvs += [vert.uvs]
        boneData += [[vert.boneIndices, vert.boneWeights]]
    return (pos, norms, uvs, boneData)

def detach(faces):
    f = []
    for face in faces:
        f += [face.points]
    return f

def makeVertexGroups(mesh, boneData):
    for vidx in range(len(boneData)):
        indices, weights = boneData[vidx]
        for idx in range(len(indices)):
            i = indices[idx]
            w = weights[idx]

            if w != 0:
                name = getBoneName(i)
                if name != None:
                    vgrp = mesh.vertex_groups.get(name)
                    if vgrp == None:
                        vgrp = mesh.vertex_groups.new(name)
                    vgrp.add([vidx], w, 'REPLACE')

def randomColor():
    randomR = random.random()
    randomG = random.random()
    randomB = random.random()
    return (randomR, randomG, randomB)

def bindMaterials(meshes, data, materials):
    if materials == None:
        return
    for i, obj in enumerate(meshes):
        mesh = obj.data
        meshData = data.meshes[i]
        if materials != None and meshData.materialKey in materials[1]:
            mesh.materials.clear()
            mesh.materials.append(materials[1][meshData.materialKey])

def bindMaterialsUniq(meshes, data, materials):
    if materials == None:
        return
    for i, obj in enumerate(meshes):
        mesh = obj.data
        meshData = data.meshes[i]
        if materials != None and meshData.materialKey in materials[1]:
            mesh.materials.clear()
            mesh.materials.append(None)
            obj.material_slots[0].link = 'OBJECT'
            obj.material_slots[0].material = materials[1][meshData.materialKey]

def importMesh(armature, meshData):
    global settings
    global rootObject
    mesh = bpy.data.meshes.new(meshData.name)
    obj = bpy.data.objects.new(mesh.name, mesh)
    obj.parent = rootObject
    bpyhelper.scene_link(obj)

    pos, norms, uvs, boneData = segregate(meshData.vertices)
    faces = detach(meshData.indices)
    mesh.from_pydata(pos, [], faces)
    mesh.polygons.foreach_set('use_smooth', [True] * len(mesh.polygons))
    for i in range(meshData.uvCount):
        bpyhelper.new_uv_layer(mesh, "UVMap%d" % (i + 1))

    if armature:
        mod = obj.modifiers.new(type="ARMATURE", name="Armature")
        mod.use_vertex_groups = True
        mod.object = armature
        obj.parent = armature

        makeVertexGroups(obj, boneData)

        current_theme = bpy.context.user_preferences.themes.items()[0][0]
        theme = bpy.context.user_preferences.themes[current_theme]

        bgrp = armature.pose.bone_groups.new(obj.name)
        bgrp.color_set = 'CUSTOM'
        bgrp.colors.normal = (randomColor())
        bgrp.colors.select = theme.view_3d.bone_pose
        bgrp.colors.active = theme.view_3d.bone_pose_active

        vgrps = obj.vertex_groups.keys()
        pbones = armature.pose.bones
        for bname in vgrps:
            pbones[bname].bone_group = bgrp

    bm = bmesh.new()
    bm.from_mesh(mesh)
    for fidx, face in enumerate(bm.faces):
        fraw = faces[fidx]
        for vidx, vert in enumerate(face.loops):
            ridx = fraw[vidx]
            for idx in range(len(mesh.uv_layers)):
                layer = bm.loops.layers.uv[idx]
                vert[layer].uv = Vector([uvs[ridx][idx][0] + settings.uvDisplaceX, 1 + settings.uvDisplaceY - uvs[ridx][idx][1]])
    bm.to_mesh(mesh)

    mesh.update()

    bpyhelper.select_obj(obj, True)
    if settings.importNormals:
        mesh.create_normals_split()
        mesh.validate(clean_customdata = False)
        mesh.update(calc_edges = True)
        mesh.normals_split_custom_set_from_vertices(norms)
        mesh.use_auto_smooth = True
    else:
        mesh.validate()

    return obj


def importMeshes(armature):
    global data
    meshes = [importMesh(armature, meshData) for meshData in data.meshes]
    return meshes

def importEmpties(armature = None):
    global data
    global settings
    global rootObject

    if not settings.importEmpties:
        return []

    att = bpy.data.objects.new('Empties', None)
    att.parent = rootObject
    att.hide = att.hide_render = True
    bpyhelper.scene_link(att)

    e_dict = {}
    for emp in data.empties:
        bpy.ops.object.empty_add(type='CIRCLE', radius=0.05 )
        empty = bpy.context.active_object
        empty.parent = att
        empty.name = emp.name
        empty.show_x_ray = True
        empty.location = xzy(emp.position)
        empty.rotation_euler = wxzy(emp.rotation).to_euler('XYZ')
        bpyhelper.select_obj(empty, True)
        if len(emp.hardpoint) > 0 and armature is not None:
            childOf = empty.constraints.new("CHILD_OF")
            childOf.name = "ChildOfHardpoint%s" % (empty.name)
            childOf.target = armature
            childOf.subtarget = emp.hardpoint
            context_cpy = bpy.context.copy()
            context_cpy["constraint"] = childOf
            empty.update_tag({"DATA"})
            bpy.ops.constraint.childof_set_inverse(context_cpy, constraint=childOf.name, owner="OBJECT")
            empty.update_tag({"DATA"})
        e_dict[empty.name] = empty
    return att, e_dict


def boneTailMiddleObject(armature):
    bpyhelper.scene_active_set(armature)
    bpy.ops.object.mode_set(mode='EDIT', toggle=False)
    eb = armature.data.edit_bones
    boneTailMiddle(eb)
    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)

def boneTailMiddle(eb):
    for bone in eb:
        if len(bone.children) > 0:
            bone.tail = Vector(map(sum,zip(*(child.head.xyz for child in bone.children))))/len(bone.children)
        else:
            if bone.parent != None:
                if bone.head.xyz != bone.parent.tail.xyz:
                    delta = bone.head.xyz - bone.parent.tail.xyz
                else:
                    delta = bone.parent.tail.xyz - bone.parent.head.xyz
                bone.tail = bone.head.xyz + delta
    for bone in eb:
        fixLength(bone)
        if bone.parent:
            if bone.head == bone.parent.tail:
                bone.use_connect = True

def select_all(ob):
    bpyhelper.select_obj(ob, True)
    for obj in ob.children: select_all(obj)

def readmdl(materials = None, rotate=True):
    global root
    global data
    global rootObject
    root, file = os.path.split(settings.filename)

    data = read_owmdl.read(settings.filename)
    if not data: return None

    rootName = os.path.splitext(file)[0]
    if len(data.header.name) > 0:
        rootName = data.header.name

    rootObject = bpy.data.objects.new(rootName, None)
    rootObject.hide = rootObject.hide_render = True
    bpyhelper.scene_link(rootObject)

    armature = None
    if settings.importSkeleton and data.header.boneCount > 0:
##        new_armature = importRefposeArmature(settings.autoIk)
##        new_armature.name = rootName + '_Skeleton'
##        new_armature.parent = rootObject
        
        armature = importArmature(settings.autoIk)
        armature.name = rootName + '_Skeleton' # _UNREFPOSE
        armature.parent = rootObject
        if rotate: armature.rotation_euler = (radians(90), 0, 0)
    meshes = importMeshes(armature)

    impMat = False
    materials = None
    if materials == None and settings.importMaterial and len(data.header.material) > 0:
        impMat = True
        matpath = data.header.material
        if not os.path.isabs(matpath):
            matpath = os.path.normpath('%s/%s' % (root, matpath))
        materials = import_owmat.read(matpath, '', settings.importTexNormal, settings.importTexEffect)
        bindMaterials(meshes, data, materials)

    empties = []
    if settings.importEmpties and data.header.emptyCount > 0:
        empties = importEmpties(armature)
        if rotate: empties[0].rotation_euler = (radians(90), 0, 0)

    if armature:
        boneTailMiddleObject(armature)

    if impMat:
        import_owmat.cleanUnusedMaterials(materials)

    if len(data.cloths) > 0:
        for cloth in data.cloths:
            bpy.ops.object.select_all(action='DESELECT')
            i = 0
            for clothSubmesh in cloth.meshes:
                submesh = meshes[clothSubmesh.id]
                if i == 0:
                    bpy.context.scene.objects.active = submesh
                bpyhelper.select_obj(submesh, True)
                vgrp = submesh.vertex_groups.new("clothPin")
                vgrp.add(clothSubmesh.pinnedVerts, 1.0, 'REPLACE')
                i += 1

            bpy.ops.object.join()
            bpy.context.object.name = cloth.name
            bpy.ops.object.select_all(action='DESELECT')

            # do it manually because I don't want to be responsible for broken models:
            # https://i.imgur.com/6Jxg91T.png?1
            # bpy.context.scene.objects.active = mainObj
            # bpy.ops.object.editmode_toggle()
            # bpy.ops.mesh.select_all(action='SELECT')
            # bpy.ops.mesh.remove_doubles()
            # bpy.ops.object.editmode_toggle()

    bpy.ops.object.select_all(action='DESELECT')
    select_all(rootObject)

    return (rootObject, armature, meshes, empties, data)

def read(aux, materials = None, mutated = False, rotate=True):
    global settings
    settings = aux

    setup()
    status = readmdl(materials, rotate)
    if not mutated:
        bpy.context.scene.update()
    finalize()
    return status

def setup():
    mode()
    bpy.ops.object.select_all(action='DESELECT')

def finalize():
    mode()

def mode():
    currentMode = bpy.context.mode
    if bpyhelper.scene_active() and currentMode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
