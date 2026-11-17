#version 300 es
in vec2 a_position;
in vec4 a_color;

uniform vec2 u_resolution;
uniform mat3 u_transform;

out vec4 v_color;

void main() {
    vec2 position = (u_transform * vec3(a_position, 1.0)).xy;
    position += u_resolution * 0.5;
    vec2 clipSpace = (position / u_resolution) * 2.0 - 1.0;
    gl_Position = vec4(clipSpace, 0.0, 1.0);
    v_color = a_color;
}
