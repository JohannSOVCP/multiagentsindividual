import GUI from 'lil-gui';
import * as twgl from 'twgl-base.js';
import '../node_modules/lil-gui/dist/lil-gui.css';
import { M3, type Mat3, type Vec2, V2 } from '../libs/2d-lib.js';
import fragmentShaderSource from './fragment.glsl?raw';
import vertexShaderSource from './vertex.glsl?raw';
import './styles.css';

interface ShapeArrays extends twgl.Arrays {
    a_position: { numComponents: 2; data: number[] };
    a_color: { numComponents: 4; data: number[] };
}

interface Mesh {
    bufferInfo: twgl.BufferInfo;
    vao: WebGLVertexArrayObject;
}

const canvasElement = document.querySelector<HTMLCanvasElement>('#canvas');
if (!canvasElement) {
    throw new Error('WebGL canvas not found.');
}
const canvas: HTMLCanvasElement = canvasElement;

const context = canvas.getContext('webgl2');
if (!context) {
    throw new Error('This browser does not support WebGL 2.');
}
const gl: WebGL2RenderingContext = context;
const programInfo = twgl.createProgramInfo(gl, [vertexShaderSource, fragmentShaderSource]);

function createMesh(arrays: ShapeArrays): Mesh {
    const bufferInfo = twgl.createBufferInfoFromArrays(gl, arrays);
    const vao = twgl.createVAOFromBufferInfo(gl, programInfo, bufferInfo);
    if (!vao) {
        throw new Error('Could not create a VertexArrayObject.');
    }
    return { bufferInfo, vao };
}

function addTriangle(
    arrays: ShapeArrays,
    a: Vec2,
    b: Vec2,
    c: Vec2,
    color: [number, number, number, number],
): void {
    arrays.a_position.data.push(a[0], a[1], b[0], b[1], c[0], c[1]);
    for (let i = 0; i < 3; i++) {
        arrays.a_color.data.push(...color);
    }
}

function emptyArrays(): ShapeArrays {
    return {
        a_position: { numComponents: 2, data: [] },
        a_color: { numComponents: 4, data: [] },
    };
}

function createFaceArrays(): ShapeArrays {
    const arrays = emptyArrays();
    const yellow: [number, number, number, number] = [1, 0.84, 0.08, 1];
    const dark: [number, number, number, number] = [0.12, 0.15, 0.22, 1];

    const segments = 24;
    const radius = 145;
    const center = V2.create(0, 0);
    for (let i = 0; i < segments; i++) {
        const firstAngle = (i / segments) * Math.PI * 2;
        const secondAngle = ((i + 1) / segments) * Math.PI * 2;
        addTriangle(
            arrays,
            center,
            V2.create(Math.cos(firstAngle) * radius, Math.sin(firstAngle) * radius),
            V2.create(Math.cos(secondAngle) * radius, Math.sin(secondAngle) * radius),
            yellow,
        );
    }

    addTriangle(arrays, V2.create(-86, 43), V2.create(-63, -4), V2.create(-40, 43), dark);
    addTriangle(arrays, V2.create(40, 43), V2.create(63, -4), V2.create(86, 43), dark);
    addTriangle(arrays, V2.create(-58, -45), V2.create(0, -80), V2.create(0, -63), dark);
    addTriangle(arrays, V2.create(0, -63), V2.create(0, -80), V2.create(58, -45), dark);
    return arrays;
}

function createPivotArrays(): ShapeArrays {
    const arrays = emptyArrays();
    const color: [number, number, number, number] = [0.25, 0.37, 0.55, 1];
    addTriangle(arrays, V2.create(0, 16), V2.create(16, 0), V2.create(0, -16), color);
    addTriangle(arrays, V2.create(0, 16), V2.create(0, -16), V2.create(-16, 0), color);
    return arrays;
}

const face = createMesh(createFaceArrays());
const pivot = createMesh(createPivotArrays());

const state = {
    translation: { x: 90, y: 0 },
    rotation: 0,
    scale: { x: 1, y: 1 },
    pivot: { x: -180, y: 0 },
    order: 'scale -> rotation -> translation',
};

const orders = [
    'scale -> rotation -> translation',
    'scale -> translation -> rotation',
    'translation -> scale -> rotation',
    'rotation -> translation -> scale',
    'rotation -> scale -> translation',
] as const;
type TransformName = 'scale' | 'rotation' | 'translation';

function makeTransform(name: TransformName): Mat3 {
    if (name === 'scale') {
        return M3.scale(V2.create(state.scale.x, state.scale.y));
    }
    if (name === 'translation') {
        return M3.translation(V2.create(state.translation.x, state.translation.y));
    }

    const toOrigin = M3.translation(V2.create(-state.pivot.x, -state.pivot.y));
    const rotate = M3.rotation((state.rotation * Math.PI) / 180);
    const fromOrigin = M3.translation(V2.create(state.pivot.x, state.pivot.y));
    return M3.multiply(fromOrigin, M3.multiply(rotate, toOrigin));
}

function faceTransform(): Mat3 {
    let transform = M3.identity();
    const names = state.order.split(' -> ') as TransformName[];
    for (const name of names) {
        transform = M3.multiply(makeTransform(name), transform);
    }
    return transform;
}

function drawMesh(mesh: Mesh, transform: Mat3): void {
    twgl.setUniforms(programInfo, {
        u_resolution: [canvas.width, canvas.height],
        u_transform: transform,
    });
    gl.bindVertexArray(mesh.vao);
    twgl.drawBufferInfo(gl, mesh.bufferInfo);
}

function render(): void {
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.clearColor(0.96, 0.97, 0.99, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(programInfo.program);

    drawMesh(face, faceTransform());
    drawMesh(pivot, M3.translation(V2.create(state.pivot.x, state.pivot.y)));
    gl.bindVertexArray(null);
}

const gui = new GUI({ title: 'Transforms' });
const faceFolder = gui.addFolder('Face');
const translationFolder = faceFolder.addFolder('Translation');
translationFolder.add(state.translation, 'x', -400, 400, 1).name('X').onChange(render);
translationFolder.add(state.translation, 'y', -280, 280, 1).name('Y').onChange(render);
faceFolder.add(state, 'rotation', -360, 360, 1).name('Rotation').onChange(render);
const scaleFolder = faceFolder.addFolder('Scale');
scaleFolder.add(state.scale, 'x', 0.2, 2.5, 0.05).name('X').onChange(render);
scaleFolder.add(state.scale, 'y', 0.2, 2.5, 0.05).name('Y').onChange(render);
faceFolder.add(state, 'order', [...orders]).name('Matrix order').onChange(render);

const pivotFolder = gui.addFolder('Pivot');
pivotFolder.add(state.pivot, 'x', -450, 450, 1).name('X').onChange(render);
pivotFolder.add(state.pivot, 'y', -300, 300, 1).name('Y').onChange(render);

gl.enable(gl.BLEND);
gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
render();
