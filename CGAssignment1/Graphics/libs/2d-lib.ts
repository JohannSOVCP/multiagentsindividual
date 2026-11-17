export type Vec2 = Float32Array;
export type Mat3 = number[];

export class V2 {
    static create(x: number, y: number): Vec2 {
        return new Float32Array([x, y]);
    }

    static add(a: Vec2, b: Vec2, dest: Vec2 = new Float32Array(2)): Vec2 {
        dest[0] = a[0] + b[0];
        dest[1] = a[1] + b[1];
        return dest;
    }

    static subtract(a: Vec2, b: Vec2, dest: Vec2 = new Float32Array(2)): Vec2 {
        dest[0] = a[0] - b[0];
        dest[1] = a[1] - b[1];
        return dest;
    }

    static scale(vector: Vec2, scalar: number, dest: Vec2 = new Float32Array(2)): Vec2 {
        dest[0] = vector[0] * scalar;
        dest[1] = vector[1] * scalar;
        return dest;
    }
}

export class M3 {
    static identity(): Mat3 {
        return [
            1, 0, 0,
            0, 1, 0,
            0, 0, 1,
        ];
    }

    static translation(vector: Vec2): Mat3 {
        return [
            1, 0, 0,
            0, 1, 0,
            vector[0], vector[1], 1,
        ];
    }

    static rotation(angleRadians: number): Mat3 {
        const cosine = Math.cos(angleRadians);
        const sine = Math.sin(angleRadians);
        return [
            cosine, sine, 0,
            -sine, cosine, 0,
            0, 0, 1,
        ];
    }

    static scale(vector: Vec2): Mat3 {
        return [
            vector[0], 0, 0,
            0, vector[1], 0,
            0, 0, 1,
        ];
    }

    static multiply(a: Mat3, b: Mat3): Mat3 {
        const result = new Array<number>(9);
        for (let column = 0; column < 3; column++) {
            for (let row = 0; row < 3; row++) {
                result[column * 3 + row] =
                    a[row] * b[column * 3] +
                    a[3 + row] * b[column * 3 + 1] +
                    a[6 + row] * b[column * 3 + 2];
            }
        }
        return result;
    }
}
